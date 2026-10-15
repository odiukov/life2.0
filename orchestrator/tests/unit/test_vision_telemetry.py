"""Exercise installed instrumentors in isolation from the process-wide telemetry test fixtures."""

import subprocess
import sys
import textwrap

import pytest


@pytest.mark.parametrize("langchain", [False, True])
def test_image_bytes_never_reach_langchain_or_provider_spans(langchain: bool) -> None:
    script = textwrap.dedent(
        """
        import asyncio
        import base64
        import json
        import os
        import sys

        import httpx
        from langchain_openai import ChatOpenAI
        from opentelemetry.instrumentation.langchain import LangchainInstrumentor
        from opentelemetry.instrumentation.openai import OpenAIInstrumentor
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor
        from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
        from orchestrator.adapters.vision import ChatModelImageDescriber
        from orchestrator.domain.attachments import Upload

        os.environ['TRACELOOP_TRACE_CONTENT'] = 'true'
        provider = TracerProvider()
        exporter = InMemorySpanExporter()
        provider.add_span_processor(SimpleSpanProcessor(exporter))
        OpenAIInstrumentor().instrument(tracer_provider=provider)
        if sys.argv[1] == 'True':
            LangchainInstrumentor().instrument(tracer_provider=provider)

        async def main():
            received = []
            image_received, release_image = asyncio.Event(), asyncio.Event()
            data = b'private-image-marker-7382'
            encoded = base64.b64encode(data).decode()

            async def respond(request):
                body = json.loads(request.content)
                received.append(body)
                if encoded in json.dumps(body):
                    image_received.set()
                    await release_image.wait()
                return httpx.Response(200, json={
                    'id': 'chatcmpl-test', 'object': 'chat.completion', 'created': 1,
                    'model': 'gpt-4o-mini',
                    'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': 'milk'}, 'finish_reason': 'stop'}],
                    'usage': {'prompt_tokens': 10, 'completion_tokens': 1, 'total_tokens': 11},
                })

            async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
                model = ChatOpenAI(model='gpt-4o-mini', api_key='test', http_async_client=http)
                class Models:
                    def chat_model(self, task):
                        return model

                # A positive control proves that actual instrumentation captures ordinary input.
                await model.ainvoke('before-vision-control')
                control_count = len(exporter.get_finished_spans())
                assert control_count > 0
                vision = asyncio.create_task(ChatModelImageDescriber(Models(), timeout_s=5).describe(
                    Upload('photo.jpg', 'image/jpeg', data), 'private-vision-question', 'en',
                ))
                await asyncio.wait_for(image_received.wait(), timeout=5)
                # A sibling task remains traced while the image request is still in progress.
                try:
                    await model.ainvoke('concurrent-text-control')
                finally:
                    release_image.set()
                assert await vision == 'milk'
                assert len(exporter.get_finished_spans()) == control_count * 2
                await model.ainvoke('after-vision-control')

            assert any(encoded in json.dumps(body) for body in received)
            assert any('private-vision-question' in json.dumps(body) for body in received)
            provider.force_flush()
            spans = exporter.get_finished_spans()
            recorded = '\\n'.join(span.to_json() for span in spans)
            assert 'before-vision-control' in recorded
            assert 'concurrent-text-control' in recorded
            assert 'after-vision-control' in recorded
            assert encoded not in recorded
            assert 'private-image-marker-7382' not in recorded
            assert 'data:image/jpeg;base64,' not in recorded
            assert 'private-vision-question' not in recorded
            scope = 'langchain' if sys.argv[1] == 'True' else 'openai'
            assert any(scope in span.instrumentation_scope.name for span in spans)
            assert len(spans) == control_count * 3
            provider.shutdown()

        asyncio.run(main())
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", script, str(langchain)], capture_output=True, text=True, timeout=30
    )
    assert result.returncode == 0, result.stderr
