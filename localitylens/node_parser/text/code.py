"""
Code splitter from llama index

Modified to make it work in non llama index places
"""

from typing import Any, Callable, List, Optional

from pydantic import Field
from localitylens.node_parser.text.interface import TextSplitter
from localitylens.node_parser.node_utils import default_id_func
from localitylens.node_parser.text.schema import Document

DEFAULT_CHUNK_LINES = 40
DEFAULT_LINES_OVERLAP = 15
DEFAULT_MAX_CHARS = 1500


class CodeSplitter(TextSplitter, extra='allow'):
    """Split code using a AST parser.

    Thank you to Kevin Lu / SweepAI for suggesting this elegant code splitting solution.
    https://docs.sweep.dev/blogs/chunking-2m-files
    """

    language: str = Field(
        description="The programming language of the code being split."
    )
    chunk_lines: int = Field(
        default=DEFAULT_CHUNK_LINES,
        description="The number of lines to include in each chunk.",
        gt=0,
    )
    chunk_lines_overlap: int = Field(
        default=DEFAULT_LINES_OVERLAP,
        description="How many lines of code each chunk overlaps with.",
        gt=0,
    )
    max_chars: int = Field(
        default=DEFAULT_MAX_CHARS,
        description="Maximum number of characters per chunk.",
        gt=0,
    )

    _parser: Callable[[str], List[str]] = Field(
        description="Code parser"
    )

    def __init__(
        self,
        language: str,
        chunk_lines: int = DEFAULT_CHUNK_LINES,
        chunk_lines_overlap: int = DEFAULT_LINES_OVERLAP,
        max_chars: int = DEFAULT_MAX_CHARS,
        parser: Any = None,
        include_metadata: bool = True,
        include_prev_next_rel: bool = True,
        id_func: Optional[Callable[[int, Document], str]] = None,
    ) -> None:
        """Initialize a CodeSplitter."""
        from tree_sitter import Parser  # pants: no-infer-dep

        if parser is None:
            try:
                import tree_sitter_languages  # pants: no-infer-dep

                parser = tree_sitter_languages.get_parser(language)
            except ImportError:
                raise ImportError(
                    "Please install tree_sitter_languages to use CodeSplitter."
                    "Or pass in a parser object."
                )
            except Exception:
                print(
                    f"Could not get parser for language {language}. Check "
                    "https://github.com/grantjenks/py-tree-sitter-languages#license "
                    "for a list of valid languages."
                )
                raise
        if not isinstance(parser, Parser):
            raise ValueError("Parser must be a tree-sitter Parser object.")
        id_func = id_func or default_id_func

        super().__init__(
            language=language,
            chunk_lines=chunk_lines,
            chunk_lines_overlap=chunk_lines_overlap,
            max_chars=max_chars,
            include_metadata=include_metadata,
            include_prev_next_rel=include_prev_next_rel,
            id_func=id_func,
            _parser=parser
        )

    @classmethod
    def from_defaults(
        cls,
        language: str,
        chunk_lines: int = DEFAULT_CHUNK_LINES,
        chunk_lines_overlap: int = DEFAULT_LINES_OVERLAP,
        max_chars: int = DEFAULT_MAX_CHARS,
        parser: Any = None,
    ) -> "CodeSplitter":
        """Create a CodeSplitter with default values."""
        return cls(
            language=language,
            chunk_lines=chunk_lines,
            chunk_lines_overlap=chunk_lines_overlap,
            max_chars=max_chars,
            parser=parser,
        )

    @classmethod
    def class_name(cls) -> str:
        return "CodeSplitter"

    def _chunk_node(self, node: Any, text: str, last_end: int = 0) -> List[str]:
        new_chunks = []
        current_chunk = ""
        for child in node.children:
            if child.end_byte - child.start_byte > self.max_chars:
                # Child is too big, recursively chunk the child
                if len(current_chunk) > 0:
                    new_chunks.append(current_chunk)
                current_chunk = ""
                new_chunks.extend(self._chunk_node(child, text, last_end))
            elif (
                len(current_chunk) + child.end_byte - child.start_byte > self.max_chars
            ):
                # Child would make the current chunk too big, so start a new chunk
                new_chunks.append(current_chunk)
                current_chunk = text[last_end : child.end_byte]
            else:
                current_chunk += text[last_end : child.end_byte]
            last_end = child.end_byte
        if len(current_chunk) > 0:
            new_chunks.append(current_chunk)
        return new_chunks

    def split_text(self, text: str) -> List[str]:
        """Split incoming code and return chunks using the AST."""
        tree = self._parser.parse(bytes(text, "utf-8"))

        if (
            not tree.root_node.children
            or tree.root_node.children[0].type != "ERROR"
        ):
            chunks = [
                chunk.strip() for chunk in self._chunk_node(tree.root_node, text)
            ]

            return chunks
        else:
            raise ValueError(f"Could not parse code with language {self.language}.")

        # TODO: set up auto-language detection using something like https://github.com/yoeo/guesslang.