"""Controller connecting the token viewer model to the application views."""

from token_viewer.controller import CommandError, Controller
from token_viewer.model import ModelError, TokenViewerModel
from token_viewer.view_models import (
    CaptureView,
    Message,
    TokenView,
    TokenizerView,
    ViewModel,
    ViewOption,
)


class RealController(Controller):
    """Controller for the real Hugging Face tokenizer model."""

    def __init__(self) -> None:
        """Create a controller with a fresh model."""
        self._model = TokenViewerModel()

    def view_model(self) -> ViewModel:
        """Build the current view-model from the domain model."""
        model = self._model

        tokenizer_view: TokenizerView | None = None
        if model.repository is not None and model.revision is not None:
            tokenizer_view = TokenizerView(
                repository=model.repository,
                revision=model.revision,
            )

        model_views = model.views()
        tokens = [
            TokenView(
                index=index,
                id=token.token_id,
                piece=token.piece,
                text=token.text,
                start=token.start,
                end=token.end,
                special=token.special,
            )
            for index, token in enumerate(model.current_tokens())
        ]

        selected: TokenView | None = None
        selected_token = model.selected_token
        if selected_token is not None:
            selected_index = model.selected
            if selected_index is None:
                raise RuntimeError("The model has a selected token without an index.")

            selected = TokenView(
                index=selected_index,
                id=selected_token.token_id,
                piece=selected_token.piece,
                text=selected_token.text,
                start=selected_token.start,
                end=selected_token.end,
                special=selected_token.special,
            )

        capture: CaptureView | None = None

        if model.capture_name is not None:
            metadata = model.capture_metadata
            capture = CaptureView(
                name=model.capture_name,
                answer=model.capture_answer,
                reasoning=model.capture_reasoning,
                requested_model=metadata.get("requested_model"),
                reported_model=metadata.get("reported_model"),
                status_code=metadata.get("status_code"),
                finish_reason=metadata.get("finish_reason"),
                usage=metadata.get("usage"),
                elapsed_seconds=metadata.get("elapsed_seconds"),
            )

        return ViewModel(
            tokenizer=tokenizer_view,
            notice=None,
            messages=[
                Message(role=role, content=content)
                for role, content in model.messages
            ],
            views=[
                ViewOption(key=view.key, title=view.title)
                for view in model_views
            ],
            current_view=model.current_view,
            text=model.current_text(),
            tokens=tokens,
            selected=selected,
            capture=capture,
        )

    def load_model(self, repository: str, revision: str) -> ViewModel:
        """Load a tokenizer and return the resulting view-model."""
        try:
            self._model.load_model(repository, revision)
        except ModelError as error:
            raise CommandError(str(error)) from error
        return self.view_model()

    def set_messages(self, messages: list[Message]) -> ViewModel:
        """Set messages and return the tokenized view-model."""
        try:
            self._model.set_messages(
                [(message.role, message.content) for message in messages]
            )
        except ModelError as error:
            raise CommandError(str(error)) from error
        return self.view_model()

    def select_view(self, key: str) -> ViewModel:
        """Select a tokenized view."""
        try:
            self._model.select_view(key)
        except ModelError as error:
            raise CommandError(str(error)) from error
        return self.view_model()

    def select_token(self, index: int) -> ViewModel:
        """Select a token in the current view."""
        try:
            self._model.select_token(index)
        except ModelError as error:
            raise CommandError(str(error)) from error
        return self.view_model()

    def load_capture(self, name: str, content: str) -> ViewModel:
        """Load a provider response capture."""
        try:
            self._model.load_capture(name, content)
        except ModelError as error:
            raise CommandError(str(error)) from error
        return self.view_model()