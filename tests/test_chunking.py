from app.services.chunking import MIN_CHUNK_CHARS, chunk_text


def test_a_short_document_stays_whole():
    text = "Refunds are issued within 5 business days of an approved request."
    assert chunk_text(text) == [text]


def test_empty_input_produces_nothing_to_embed():
    # Not [""] - a blank chunk would become a meaningless vector that can
    # still be returned by a similarity search.
    assert chunk_text("") == []
    assert chunk_text("   \n\n  ") == []
    assert chunk_text(None) == []  # type: ignore[arg-type]


def test_a_long_document_is_split():
    text = "\n\n".join(f"Paragraph {i}. " + "word " * 40 for i in range(10))
    chunks = chunk_text(text, target_chars=400)
    assert len(chunks) > 1
    assert all(chunk.strip() for chunk in chunks)


def test_chunks_respect_the_target_size():
    text = "\n\n".join("Sentence about shipping. " * 8 for _ in range(6))
    target = 500
    chunks = chunk_text(text, target_chars=target, overlap_chars=80)
    # Overlap is added on top of the target, so allow for it.
    assert all(len(chunk) <= target + 80 + 50 for chunk in chunks)


def test_splitting_prefers_paragraph_boundaries():
    """A chunk that ends mid-clause reads badly when quoted as a citation."""
    paragraphs = [
        "Standard shipping takes 3-5 business days and costs a flat $6.95.",
        "International shipping takes 7-14 business days to Canada and the UK.",
        "Returns are accepted within 60 days if the item is unused.",
    ]
    chunks = chunk_text("\n\n".join(paragraphs), target_chars=80)
    # Each paragraph is under the target, so none should be cut apart.
    for paragraph in paragraphs:
        assert any(paragraph in chunk for chunk in chunks), f"{paragraph!r} was split"


def test_an_over_long_paragraph_falls_back_to_sentences():
    sentences = [f"This is sentence number {i} about our returns policy." for i in range(12)]
    chunks = chunk_text(" ".join(sentences), target_chars=200)
    assert len(chunks) > 1
    for sentence in sentences:
        assert any(sentence in chunk for chunk in chunks), f"{sentence!r} was cut apart"


def test_a_sentence_longer_than_a_chunk_is_still_handled():
    """A pasted table or a wall of text with no punctuation must not hang or
    produce one enormous chunk."""
    monster = "word" * 500  # 2000 chars, no spaces or punctuation
    chunks = chunk_text(monster, target_chars=300, overlap_chars=60)
    assert len(chunks) > 1
    # Overlap is added on top of the target by design, so the bound is
    # target + overlap rather than target.
    assert all(len(chunk) <= 300 + 60 for chunk in chunks)


def test_nothing_is_lost_when_splitting_text_with_no_boundaries():
    """Checked without overlap, because overlap duplicates text on purpose
    and exact reconstruction is then meaningless."""
    monster = "word" * 500
    chunks = chunk_text(monster, target_chars=300, overlap_chars=0)
    assert "".join(chunks) == monster


def test_consecutive_chunks_overlap():
    """A fact spanning a boundary should appear whole in at least one chunk."""
    text = "\n\n".join(f"Fact {i} about the policy and its conditions." for i in range(20))
    chunks = chunk_text(text, target_chars=200, overlap_chars=60)
    assert len(chunks) > 1
    # The start of a later chunk should repeat some of the previous one.
    assert any(chunks[i][-30:].strip() and chunks[i][-30:].strip()[:15] in chunks[i + 1]
               for i in range(len(chunks) - 1))


def test_overlap_can_be_switched_off():
    text = "\n\n".join(f"Paragraph {i} text here." for i in range(20))
    chunks = chunk_text(text, target_chars=150, overlap_chars=0)
    assert len(chunks) > 1


def test_no_tiny_trailing_fragment_is_left_behind():
    """A stub chunk retrieves poorly and clutters the citation list."""
    text = "\n\n".join(["Body paragraph with a reasonable amount of text in it." * 3] * 4)
    text += "\n\nOk."
    chunks = chunk_text(text, target_chars=300)
    assert all(len(chunk) >= MIN_CHUNK_CHARS for chunk in chunks) or len(chunks) == 1


def test_all_of_the_original_text_survives():
    paragraphs = [f"Unique marker {i}. Some policy detail follows here." for i in range(15)]
    chunks = chunk_text("\n\n".join(paragraphs), target_chars=250)
    combined = " ".join(chunks)
    for i in range(15):
        assert f"Unique marker {i}." in combined, f"marker {i} was lost"
