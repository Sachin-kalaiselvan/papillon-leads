"""The phone call. Exotel streams audio over a WebSocket; Pipecat runs STT → LLM → TTS on it."""

from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import parse_qs

from fastapi import WebSocket
from loguru import logger
from pipecat.adapters.llm.schemas.function_schema import FunctionSchema
from pipecat.adapters.llm.schemas.tools_schema import ToolsSchema
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import EndWorkerFrame, TTSSpeakFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import LLMContextAggregatorPair, LLMUserAggregatorParams
from pipecat.processors.frame_processor import FrameDirection
from pipecat.runner.utils import parse_telephony_websocket
from pipecat.serializers.exotel import ExotelFrameSerializer
from pipecat.services.llm_service import FunctionCallParams
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.transports.websocket.fastapi import FastAPIWebsocketParams, FastAPIWebsocketTransport
from pipecat.workers.runner import WorkerRunner

from . import db
from .config import cfg
from .dialer import verify
from .qualifier import END_PROPS, SAVE_PROPS, apply_details, finalize, greeting, system_prompt


def _stt():
    if cfg.stt_provider == "sarvam":
        from pipecat.services.sarvam.stt import SarvamSTTService
        return SarvamSTTService(api_key=cfg.sarvam_api_key)
    from pipecat.services.deepgram.stt import DeepgramSTTService
    # nova-3 "multi" handles Indian English with Hindi words mixed in
    return DeepgramSTTService(api_key=cfg.deepgram_api_key,
                              settings=DeepgramSTTService.Settings(model="nova-3", language="multi",
                                                                   smart_format=True, numerals=True))


def _tts():
    if cfg.tts_provider == "cartesia":
        from pipecat.services.cartesia.tts import CartesiaTTSService
        return CartesiaTTSService(api_key=cfg.cartesia_api_key, voice_id=cfg.cartesia_voice)
    from pipecat.services.sarvam.tts import SarvamTTSService
    return SarvamTTSService(api_key=cfg.sarvam_api_key,
                            settings=SarvamTTSService.Settings(model=cfg.sarvam_tts_model, voice=cfg.sarvam_voice,
                                                               language="en-IN"))


def _custom_params(call_data) -> dict:
    cp = getattr(call_data, "custom_parameters", None) or {}
    if isinstance(cp, str):
        cp = {k: v[0] for k, v in parse_qs(cp.lstrip("?")).items()}
    return cp


async def run_call(websocket: WebSocket) -> None:
    await websocket.accept()
    _, call_data = await parse_telephony_websocket(websocket)
    params = _custom_params(call_data)
    lead_id, call_id, sig = params.get("lead"), params.get("call"), params.get("sig")
    if not (lead_id and call_id and verify(lead_id, call_id, sig or "")):
        # fall back to looking the call up by Exotel's CallSid
        row = await db.fetchone("select id, lead_id from calls where provider_call_id = %s", [call_data.call_id])
        if not row:
            logger.warning("Rejected stream: unknown call {}", call_data.call_id)
            await websocket.close()
            return
        lead_id, call_id = str(row["lead_id"]), str(row["id"])

    lead = await db.get_lead(lead_id)
    await db.execute("update calls set status = 'in_progress', answered_at = coalesce(answered_at, now()), "
                     "provider_call_id = coalesce(provider_call_id, %s) where id = %s", [call_data.call_id, call_id])
    await db.log_event(lead_id, "call_answered", {"call_id": call_id})

    transport = FastAPIWebsocketTransport(
        websocket=websocket,
        params=FastAPIWebsocketParams(
            audio_in_enabled=True, audio_out_enabled=True, add_wav_header=False,
            serializer=ExotelFrameSerializer(stream_sid=call_data.stream_id, call_sid=call_data.call_id),
        ),
    )
    state = {"ended": None}

    async def save_details(p: FunctionCallParams):
        await apply_details(lead_id, dict(p.arguments))
        await p.result_callback({"saved": True})

    async def end_conversation(p: FunctionCallParams):
        state["ended"] = dict(p.arguments)
        await p.result_callback({"ok": True})
        await p.llm.push_frame(EndWorkerFrame(), FrameDirection.UPSTREAM)

    tools = ToolsSchema(standard_tools=[
        FunctionSchema("save_details", "Save details learned about the enquiry. Call whenever you learn something.",
                       SAVE_PROPS, []),
        FunctionSchema("end_conversation", "End the call after saying goodbye.", END_PROPS, ["outcome", "summary"]),
    ])
    opening = greeting(lead)
    context = LLMContext(messages=[{"role": "system", "content": system_prompt(lead, "voice")}], tools=tools)
    agg = LLMContextAggregatorPair(context, user_params=LLMUserAggregatorParams(vad_analyzer=SileroVADAnalyzer()))
    llm = OpenAILLMService(api_key=cfg.openai_api_key,
                           settings=OpenAILLMService.Settings(model=cfg.llm_model, temperature=0.4))
    llm.register_function("save_details", save_details)
    llm.register_function("end_conversation", end_conversation)

    pipeline = Pipeline([transport.input(), _stt(), agg.user(), llm, _tts(), transport.output(), agg.assistant()])
    worker = PipelineWorker(
        pipeline,
        params=PipelineParams(audio_in_sample_rate=8000, audio_out_sample_rate=8000),
        idle_timeout_secs=45,
    )

    @transport.event_handler("on_client_connected")
    async def _connected(_t, _c):
        await worker.queue_frames([TTSSpeakFrame(opening)])

    @transport.event_handler("on_client_disconnected")
    async def _disconnected(_t, _c):
        await worker.cancel()

    started = datetime.now(timezone.utc)
    try:
        await WorkerRunner(handle_sigint=False).run(worker)
    except Exception:  # noqa: BLE001
        logger.exception("call pipeline error for lead {}", lead_id)
    finally:
        transcript = [
            {"role": m.get("role"), "text": m.get("content")}
            for m in context.get_messages()
            if isinstance(m, dict) and m.get("role") in ("user", "assistant") and isinstance(m.get("content"), str)
        ]
        ended = state["ended"] or {"outcome": "incomplete", "summary": None}
        await db.execute(
            """update calls set status = 'completed', ended_at = now(),
                 duration_sec = coalesce(duration_sec, %s), transcript = %s, outcome = %s, summary = %s where id = %s""",
            [int((datetime.now(timezone.utc) - started).total_seconds()), transcript, ended.get("outcome"),
             ended.get("summary"), call_id],
        )
        await finalize(lead_id, ended.get("outcome", "incomplete"), ended.get("summary"), ended.get("callback_iso"))
