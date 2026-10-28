"""Terminal view for the token viewer."""

from token_viewer.real_controller import RealController
from token_viewer.view_models import Message, TokenView, ViewModel


REPOSITORY = "nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-NVFP4"
REVISION = "bee7596271d1495f6992ae224aefde4410e816b8"


def print_tokens(view_model: ViewModel) -> None:
    """Print the tokens in the current view."""
    print(f"\nView: {view_model.current_view}")
    print(f"Text: {view_model.text!r}")
    print(f"Token count: {len(view_model.tokens)}")
    print()
    print("Index  ID       Piece                 Text                  Special")
    print("-" * 75)

    for token in view_model.tokens:
        print_token(token)


def print_token(token: TokenView) -> None:
    """Print one token."""
    print(
        f"{token.index:>5}  "
        f"{token.id:>6}   "
        f"{token.piece!r:<20}   "
        f"{token.text!r:<20}   "
        f"{token.special}"
    )


def main() -> None:
    """Load the course request and print both token views."""
    controller = RealController()

    controller.load_model(REPOSITORY, REVISION)

    messages = [
        Message(
            role="user",
            content="Explain tokenization in one sentence.",
        )
    ]

    view_model = controller.set_messages(messages)
    print_tokens(view_model)

    print("\nSwitching to text-only view...")
    view_model = controller.select_view("text")
    print_tokens(view_model)

    print("\nSelecting token 5...")
    view_model = controller.select_token(5)

    if view_model.selected is not None:
        print("Selected token:")
        print_token(view_model.selected)


if __name__ == "__main__":
    main()