from app.quotes import _norm, quote_in


def test_exact_match():
    source = "We decided to use SQLite for the MVP database."
    assert quote_in("use SQLite for the MVP", source)


def test_punctuation_and_case():
    source = "Let's ship the API by Friday, okay?"
    assert quote_in("lets ship the api by friday", source)
    assert quote_in("Let's ship the API by Friday", source)


def test_devanagari():
    source = "Speaker 1 [01:02]: Humne decide kiya ki pricing change nahi karenge।"
    assert quote_in("pricing change nahi karenge", source)
    # Keep Devanagari matras via M category
    source2 = "हमने फैसला किया कि प्राइसिंग नहीं बदलेंगे"
    assert quote_in("प्राइसिंग नहीं बदलेंगे", source2)


def test_too_short_rejected():
    source = "Yes we will do it tomorrow morning for sure."
    assert not quote_in("yes", source)
    assert not quote_in("ab", source)


def test_fabricated_quote_rejected():
    source = "We will keep the dark theme and large tap targets."
    assert not quote_in("we will rewrite everything in rust", source)


def test_norm_collapses_whitespace():
    assert _norm("  Hello,   World!!  ") == "hello world"
