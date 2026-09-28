"""Split a document into retrievable pieces.

Chunk size is a retrieval-quality decision, not a formatting one. Too large
and a chunk covers several topics, so the embedding is an average of all of
them and matches none precisely - and the model is handed paragraphs of
irrelevant text alongside the answer. Too small and a chunk loses the
context that makes it meaningful ("within 30 days of purchase" is useless
without knowing what it refers to).

Boundaries are chosen where the author already put them: paragraphs first,
then sentences, and only as a last resort mid-sentence. A chunk that ends
halfway through a clause reads badly when a reviewer sees it quoted as a
citation.

Consecutive chunks overlap slightly, so a fact that straddles a boundary
appears whole in at least one of them.
"""
import re

# Roughly 150-200 words. Comfortably inside the embedding model's limit,
# and close to the size of the hand-written corpus chunks that retrieve well.
DEFAULT_TARGET_CHARS = 800
DEFAULT_OVERLAP_CHARS = 120
# Below this a trailing fragment is folded back into the previous chunk
# rather than left as a stub that matches nothing useful.
MIN_CHUNK_CHARS = 120

# What separates two units joined into the same chunk.
_JOIN = "\n\n"

_PARAGRAPH = re.compile(r"\n\s*\n")
# Split after ., ! or ? when followed by whitespace and a capital or quote.
# Deliberately conservative: it leaves "Mr. Smith" and "v1.2" alone.
_SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[\"'(\[]?[A-Z0-9])")


def _hard_split(text: str, limit: int) -> list[str]:
    """Last resort for a single sentence longer than a whole chunk - a wall
    of text with no punctuation, or a pasted table."""
    return [text[i : i + limit].strip() for i in range(0, len(text), limit)]


def _split_to_units(text: str, limit: int) -> list[str]:
    """Break into the largest pieces that still fit, preferring the author's
    own boundaries."""
    units: list[str] = []
    for paragraph in _PARAGRAPH.split(text):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        if len(paragraph) <= limit:
            units.append(paragraph)
            continue
        for sentence in _SENTENCE.split(paragraph):
            sentence = sentence.strip()
            if not sentence:
                continue
            if len(sentence) <= limit:
                units.append(sentence)
            else:
                units.extend(s for s in _hard_split(sentence, limit) if s)
    return units


def chunk_text(
    text: str,
    *,
    target_chars: int = DEFAULT_TARGET_CHARS,
    overlap_chars: int = DEFAULT_OVERLAP_CHARS,
) -> list[str]:
    """Split `text` into chunks of roughly `target_chars`.

    Returns an empty list for empty input rather than a list containing an
    empty string, so a blank document produces nothing to embed instead of
    one meaningless vector.
    """
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= target_chars:
        return [text]

    # The ceiling a chunk may reach once overlap is carried in.
    max_chars = target_chars + overlap_chars

    units = _split_to_units(text, target_chars)
    if not units:
        return []

    chunks: list[str] = []
    current = ""
    for unit in units:
        if not current:
            current = unit
        elif len(current) + 1 + len(unit) <= target_chars:
            current = f"{current}\n\n{unit}" if unit[:1].isupper() else f"{current} {unit}"
        else:
            chunks.append(current)
            # Carry the tail of the finished chunk into the next one so a
            # fact spanning the boundary survives intact somewhere. Trim the
            # carried text - never the new content - if the join would push
            # the chunk past its ceiling, so chunk size stays predictable
            # for the embedding model.
            tail = current[-overlap_chars:].lstrip() if overlap_chars else ""
            if tail:
                room = max_chars - len(unit) - len(_JOIN)
                tail = tail[-room:] if room > 0 else ""
            current = f"{tail}{_JOIN}{unit}" if tail else unit
    if current:
        chunks.append(current)

    # A short final fragment retrieves poorly on its own; merge it back.
    if len(chunks) > 1 and len(chunks[-1]) < MIN_CHUNK_CHARS:
        tail = chunks.pop()
        chunks[-1] = f"{chunks[-1]}\n\n{tail}"

    return chunks
