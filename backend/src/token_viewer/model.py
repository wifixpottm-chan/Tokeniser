"""Domain model for loading and tokenizing a Hugging Face chat tokenizer."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict

from huggingface_hub import hf_hub_download
from jinja2.sandbox import ImmutableSandboxedEnvironment
from tokenizers import Tokenizer


class ModelError(Exception):
    """The model refused an operation without changing its state."""

class CaptureMetadata(TypedDict):
    """Metadata extracted from a provider capture."""

    requested_model: str | None
    reported_model: str | None
    status_code: int | None
    finish_reason: str | None
    usage: dict[str, object] | None
    elapsed_seconds: float | None

@dataclass(frozen=True)
class ModelToken:
    """One token produced by the tokenizer."""

    token_id: int
    piece: str
    text: str
    start: int
    end: int
    special: bool


@dataclass(frozen=True)
class TokenizedView:
    """One text and its token sequence."""

    key: str
    title: str
    text: str
    tokens: list[ModelToken]


class TokenViewerModel:
    """State and domain operations for the token viewer."""

    def __init__(self) -> None:
        """Create an empty model."""
        self._repository: str | None = None
        self._revision: str | None = None
        self._messages: list[tuple[str, str]] = []
        self._views: dict[str, TokenizedView] = {}
        self._current_view: str | None = None
        self._selected: int | None = None
        self._tokenizer: Tokenizer | None = None
        self._chat_template: str | None = None
        self._capture_name: str | None = None
        self._capture_answer: str | None = None
        self._capture_reasoning: str | None = None
        self._capture_metadata: CaptureMetadata = {
            "requested_model": None,
            "reported_model": None,
            "status_code": None,
            "finish_reason": None,
            "usage": None,
            "elapsed_seconds": None,
        }

    def _tokenize_view(
        self,
        key: str,
        title: str,
        text: str,
    ) -> TokenizedView:
        """Create one tokenized view using the loaded tokenizer."""
        tokenizer, _ = self._require_loaded()

        special_ids: set[int] = {
            token_id
            for token_id, added_token in tokenizer.get_added_tokens_decoder().items()
            if added_token.special
        }

        return TokenizedView(
            key=key,
            title=title,
            text=text,
            tokens=self._make_tokens(text, tokenizer, special_ids),
        )

    def load_model(self, repository: str, revision: str) -> None:
        """Load a tokenizer and chat template from a pinned repository."""
        if not repository.strip():
            raise ModelError("Give a Hugging Face repository.")
        if not revision.strip():
            raise ModelError("Give a model revision.")

        download_folder: Path = (
            Path(__file__).resolve().parents[2]
            / "downloads"
            / repository.replace("/", "--")
            / revision[:12]
        )

        tokenizer_path: str = hf_hub_download(
            repository,
            "tokenizer.json",
            revision=revision,
            local_dir=download_folder,
            token=False,
        )
        template_path: str = hf_hub_download(
            repository,
            "chat_template.jinja",
            revision=revision,
            local_dir=download_folder,
            token=False,
        )

        tokenizer: Tokenizer = Tokenizer.from_file(tokenizer_path)
        chat_template: str = Path(template_path).read_text(encoding="utf-8")

        self._repository = repository
        self._revision = revision
        self._tokenizer = tokenizer
        self._chat_template = chat_template
        self._views = {}
        self._current_view = None
        self._selected = None

    def _require_loaded(self) -> tuple[Tokenizer, str]:
        """Return the tokenizer and template, or refuse if no model is loaded."""
        if self._tokenizer is None or self._chat_template is None:
            raise ModelError("Load a tokenizer before tokenizing messages.")
        return self._tokenizer, self._chat_template

    def _make_tokens(
        self,
        text: str,
        tokenizer: Tokenizer,
        special_ids: set[int],
    ) -> list[ModelToken]:
        """Encode text and convert the result into model tokens."""
        encoding = tokenizer.encode(text, add_special_tokens=False)

        return [
            ModelToken(
                token_id=token_id,
                piece=piece,
                text=tokenizer.decode(
                    [token_id],
                    skip_special_tokens=False,
                ),
                start=start,
                end=end,
                special=token_id in special_ids,
            )
            for token_id, piece, (start, end) in zip(
                encoding.ids,
                encoding.tokens,
                encoding.offsets,
                strict=True,
            )
        ]

    def set_messages(self, messages: list[tuple[str, str]]) -> None:
        """Replace messages and tokenize the text and chat views."""
        tokenizer, chat_template = self._require_loaded()

        template_messages: list[dict[str, str]] = [
            {"role": role, "content": content}
            for role, content in messages
        ]

        text = "\n".join(content for _, content in messages)

        environment = ImmutableSandboxedEnvironment(
            trim_blocks=True,
            lstrip_blocks=True,
        )
        chat_text = environment.from_string(chat_template).render(
            messages=template_messages,
            add_generation_prompt=True,
            enable_thinking=False,
        )

        '''special_ids: set[int] = {
            token_id
            for token_id, added_token in tokenizer.get_added_tokens_decoder().items()
            if added_token.special
        }'''

        text_view = self._tokenize_view(
            key="text",
            title="Text alone",
            text=text,
        )

        chat_view = self._tokenize_view(
            key="chat",
            title="Chat, after the model template",
            text=chat_text,
        )

        new_views: dict[str, TokenizedView] = {
            "text": text_view,
            "chat": chat_view,
        }

        self._messages = list(messages)
        self._views = new_views
        self._current_view = "chat"
        self._selected = None

    def load_capture(self, name: str, content: str) -> None:
        """Parse and store a provider response capture."""
        try:
            capture = json.loads(content)
        except json.JSONDecodeError as error:
            raise ModelError("The capture is not valid JSON.") from error

        if not isinstance(capture, dict):
            raise ModelError("The capture must be a JSON object.")

        response = capture.get("response")
        if not isinstance(response, dict):
            raise ModelError("The capture has no response object.")

        response_body = response.get("body")
        if not isinstance(response_body, dict):
            raise ModelError("The response has no JSON body.")

        choices = response_body.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ModelError("The response has no choices.")

        first_choice = choices[0]
        if not isinstance(first_choice, dict):
            raise ModelError("The first response choice is invalid.")

        message = first_choice.get("message")
        if not isinstance(message, dict):
            raise ModelError("The response has no assistant message.")

        answer = message.get("content")
        reasoning = message.get("reasoning_content")

        if answer is not None and not isinstance(answer, str):
            raise ModelError("The response answer is not text.")

        if reasoning is not None and not isinstance(reasoning, str):
            raise ModelError("The response reasoning is not text.")

        request = capture.get("request")
        request_body = request.get("body") if isinstance(request, dict) else None

        requested_model: str | None = None
        if isinstance(request_body, dict):
            value = request_body.get("model")
            if isinstance(value, str):
                requested_model = value

        reported_model = response_body.get("model")
        if reported_model is not None and not isinstance(reported_model, str):
            raise ModelError("The reported model is not text.")

        status_code = response.get("status_code")
        if status_code is not None and not isinstance(status_code, int):
            raise ModelError("The response status code is invalid.")

        finish_reason = first_choice.get("finish_reason")
        if finish_reason is not None and not isinstance(finish_reason, str):
            raise ModelError("The finish reason is invalid.")

        usage = response_body.get("usage")
        if usage is not None and not isinstance(usage, dict):
            raise ModelError("The response usage is invalid.")

        elapsed_seconds = response.get("elapsed_seconds")
        if elapsed_seconds is None:
            elapsed_seconds = capture.get("waited_seconds")

        if elapsed_seconds is not None and not isinstance(
            elapsed_seconds, (int, float)
        ):
            raise ModelError("The elapsed time is invalid.")

        metadata: CaptureMetadata = {
            "requested_model": requested_model,
            "reported_model": reported_model,
            "status_code": status_code,
            "finish_reason": finish_reason,
            "usage": usage,
            "elapsed_seconds": (
            None if elapsed_seconds is None else float(elapsed_seconds)
        ),
        }

        self._capture_name = name
        self._capture_answer = answer
        self._capture_reasoning = reasoning
        self._capture_metadata = metadata

        new_views = dict(self._views)

        if answer is not None:
            new_views["answer"] = self._tokenize_view(
                key="answer",
                title="Provider answer, re-tokenized",
                text=answer,
            )

        if reasoning is not None:
            new_views["reasoning"] = self._tokenize_view(
                key="reasoning",
                title="Provider reasoning, re-tokenized",
                text=reasoning,
            )

        self._views = new_views

    def select_view(self, key: str) -> None:
        """Switch to one of the available tokenized views."""
        if key not in self._views:
            raise ModelError(f"There is no view {key!r}.")
        self._current_view = key
        self._selected = None

    def select_token(self, index: int) -> None:
        """Select one token in the current view."""
        tokens = self.current_tokens()
        if not 0 <= index < len(tokens):
            raise ModelError(
                f"There is no token {index}: this view has "
                f"{len(tokens)}, numbered from 0."
            )
        self._selected = index

    @property
    def selected_token(self) -> ModelToken | None:
        """Return the selected token, if one exists."""
        if self._selected is None:
            return None
        return self.current_tokens()[self._selected]

    @property
    def capture_answer(self) -> str | None:
        """Return the captured answer."""
        return self._capture_answer
    
    @property
    def capture_reasoning(self) -> str | None:
        """Return the captured reasoning."""
        return self._capture_reasoning
    
    @property
    def capture_metadata(self) -> CaptureMetadata:
        """Return the captured response metadata."""
        return self._capture_metadata.copy()
    
    @property
    def repository(self) -> str | None:
        """Return the loaded Hugging Face repository."""
        return self._repository

    @property
    def revision(self) -> str | None:
        """Return the loaded revision."""
        return self._revision

    @property
    def messages(self) -> list[tuple[str, str]]:
        """Return the current messages."""
        return list(self._messages)

    @property
    def current_view(self) -> str | None:
        """Return the key of the current view."""
        return self._current_view

    @property
    def selected(self) -> int | None:
        """Return the selected token index."""
        return self._selected

    @property
    def capture_name(self) -> str | None:
        """Return the loaded capture name."""
        return self._capture_name

    def views(self) -> list[TokenizedView]:
        """Return all available tokenized views."""
        return list(self._views.values())

    def current_tokens(self) -> list[ModelToken]:
        """Return the tokens of the current view."""
        if self._current_view is None:
            return []
        return self._views[self._current_view].tokens

    def current_text(self) -> str:
        """Return the text of the current view."""
        if self._current_view is None:
            return ""
        return self._views[self._current_view].text
    