from voiceover.config import apply_pronunciations, load_script

RULES = {"AutoKool": "Auto Koul", "FCFA": "francs CFA"}


def test_replaces_whole_words():
    assert apply_pronunciations("Voici AutoKool.", RULES) == "Voici Auto Koul."
    assert apply_pronunciations("15 000 FCFA par mois", RULES) == "15 000 francs CFA par mois"


def test_does_not_replace_inside_words():
    assert apply_pronunciations("AutoKoolPro et XFCFA", RULES) == "AutoKoolPro et XFCFA"


def test_is_case_sensitive():
    assert apply_pronunciations("autokool", RULES) == "autokool"


def test_longest_key_wins_and_no_cascading():
    rules = {"CFA": "C F A", "FCFA": "francs CFA"}
    # FCFA is replaced once; the 'CFA' produced by the replacement is not re-processed.
    assert apply_pronunciations("FCFA et CFA", rules) == "francs CFA et C F A"


def test_handles_regex_special_characters():
    assert apply_pronunciations("Prix: 5$ (TTC)", {"5$": "cinq dollars"}) == "Prix: cinq dollars (TTC)"


def test_empty_rules_is_identity():
    assert apply_pronunciations("Voici AutoKool.", {}) == "Voici AutoKool."


def test_script_prepared_text(script_file):
    script = load_script(script_file)
    assert script.prepared_text(script.segments[1]) == "Voici Auto Koul, dès quinze mille francs CFA."
