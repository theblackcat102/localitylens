from typing import Callable, Optional

global_tokenizer: Optional[Callable[[str], list]] = None