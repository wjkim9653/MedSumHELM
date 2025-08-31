# mypy: check_untyped_defs = False
import base64
from typing import Any, Dict, List, Optional, Union, cast

import google.generativeai as genai

from helm.common.cache import CacheConfig
from helm.common.request import (
    Request,
    RequestResult,
    GeneratedOutput,
    Token,
    ErrorFlags,
)
from helm.common.tokenization_request import (
    TokenizationRequest,
    TokenizationRequestResult,
)
from helm.common.hierarchical_logger import hlog, hwarn
from helm.common.media_object import TEXT_TYPE
from helm.clients.client import CachingClient, truncate_sequence, generate_uid_for_multimodal_prompt
from helm.tokenizers.tokenizer import Tokenizer


class GeminiClient(CachingClient):
    """Google Gemini API Client compatible with OpenAIClient interface"""

    def __init__(
        self,
        tokenizer: Tokenizer,
        tokenizer_name: str,
        cache_config: CacheConfig,
        api_key: Optional[str] = None,
        gemini_model_name: Optional[str] = None,
        **kwargs,
    ):
        super().__init__(cache_config=cache_config)
        if not api_key:
            raise ValueError("Gemini API key is required")
        genai.configure(api_key=api_key)
        self.model_name = gemini_model_name
        self.tokenizer = tokenizer
        self.tokenizer_name = tokenizer_name
        self.model = genai.GenerativeModel(self.model_name)

    def _get_model_for_request(self, request: Request) -> str:
        return self.model_name or request.model_engine

    def _get_cache_key(self, raw_request: Dict, request: Request):
        cache_key = CachingClient.make_cache_key(raw_request, request)
        if request.multimodal_prompt:
            prompt_key: str = generate_uid_for_multimodal_prompt(request.multimodal_prompt)
            cache_key = {**cache_key, "multimodal_prompt": prompt_key}
        return cache_key

    def _make_chat_raw_request(self, request: Request) -> Dict[str, Any]:
        """Convert HELM Request into Gemini generate_content format."""
        contents: List[Dict[str, Any]] = []

        if request.messages:
            for msg in request.messages:
                role = msg.get("role")
                content = msg.get("content")
                parts = []
                if isinstance(content, str):
                    parts.append({"text": content})
                elif isinstance(content, list):
                    # already in Gemini parts format?
                    parts.extend(content)
                contents.append({"role": role, "parts": parts})

        elif request.multimodal_prompt:
            request.validate()
            parts = []
            for media_object in request.multimodal_prompt.media_objects:
                if media_object.is_type(TEXT_TYPE):
                    parts.append({"text": media_object.text})
                elif media_object.is_type("image") and media_object.location:
                    with open(media_object.location, "rb") as f:
                        img_b64 = base64.b64encode(f.read()).decode("utf-8")
                    parts.append({
                        "inline_data": {
                            "mime_type": media_object.content_type,
                            "data": img_b64
                        }
                    })
                else:
                    raise ValueError(f"Unsupported media type for Gemini: {media_object.type}")
            contents.append({"role": "user", "parts": parts})

        else:
            contents.append({"role": "user", "parts": [{"text": request.prompt}]})

        raw_request: Dict[str, Any] = {
            "contents": contents,
            "generation_config": {
                "temperature": request.temperature,
                "top_p": request.top_p,
                "max_output_tokens": request.max_tokens,
            },
        }
        return raw_request

    def _make_chat_request(self, request: Request) -> RequestResult:
        raw_request = self._make_chat_raw_request(request)

        def do_it() -> Dict[str, Any]:
            resp = self.model.generate_content(**raw_request)
            return resp.to_dict()

        try:
            cache_key = self._get_cache_key(raw_request, request)
            response, cached = self.cache.get(cache_key, do_it)
        except Exception as e:
            hwarn(f"Gemini API error: {e}")
            return RequestResult(
                success=False,
                cached=False,
                error=str(e),
                completions=[],
                embedding=[],
                error_flags=ErrorFlags(is_retriable=False, is_fatal=False),
            )

        completions: List[GeneratedOutput] = []
        for cand in response.get("candidates", []):
            text_parts = [p.get("text", "") for p in cand.get("content", {}).get("parts", [])]
            text = "".join(text_parts)

            # finish_reason mapping
            finish_reason = cand.get("finish_reason", "")
            if finish_reason:
                finish_reason = finish_reason.lower()

            # Tokenization (Gemini does not return tokens/logprobs)
            tokenization_result: TokenizationRequestResult = self.tokenizer.tokenize(
                TokenizationRequest(text, tokenizer=self.tokenizer_name)
            )
            tokens: List[Token] = [
                Token(text=cast(str, raw_token), logprob=0) for raw_token in tokenization_result.raw_tokens
            ]

            if request.echo_prompt:
                text = request.prompt + text

            completion = GeneratedOutput(
                text=text,
                logprob=0,
                tokens=tokens,
                finish_reason={"reason": finish_reason},
            )
            completions.append(truncate_sequence(completion, request))

        return RequestResult(
            success=True,
            cached=cached,
            request_time=None,
            request_datetime=None,
            completions=completions,
            embedding=[],
        )

    def _make_embedding_request(self, request: Request) -> RequestResult:
        def do_it() -> Dict[str, Any]:
            return genai.embed_content(model="models/embedding-001", content=request.prompt)

        try:
            cache_key = self._get_cache_key({"prompt": request.prompt}, request)
            response, cached = self.cache.get(cache_key, do_it)
        except Exception as e:
            return RequestResult(success=False, cached=False, error=str(e), completions=[], embedding=[])

        embedding = response["embedding"]["values"]
        return RequestResult(
            success=True,
            cached=cached,
            request_time=None,
            request_datetime=None,
            completions=[],
            embedding=embedding,
        )

    def make_request(self, request: Request) -> RequestResult:
        if request.embedding:
            return self._make_embedding_request(request)
        else:
            return self._make_chat_request(request)
