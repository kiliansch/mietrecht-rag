"""The single evaluation dataset for the Mietrecht agent.

Each item's `collection` field names the hybrid-retrieval collection
(`config.STATUTES_COLLECTION` or `config.CASE_LAW_COLLECTION`) that is expected
to answer it; `src.eval.runner` uses this both to score the agent end-to-end
and to score that collection's hybrid retriever in isolation.

Q7 is a planted hallucination (20%-rule misconception) used to verify that
`faithfulness` catches an answer that is NOT grounded in the retrieved
context, even though it sounds plausible.
"""

from __future__ import annotations

from typing import Any

from src import config

EVAL_DATASET: list[dict[str, Any]] = [
    {
        "question": "Welche Pflichten hat der Vermieter gemäß § 535 Abs. 1 BGB gegenüber dem Mieter?",
        "answer": (
            "Der Vermieter ist verpflichtet, dem Mieter die Mietsache in einem "
            "zum vertragsgemäßen Gebrauch geeigneten Zustand zu überlassen und "
            "sie in diesem Zustand zu erhalten."
        ),
        "ground_truth": (
            "Der Vermieter muss die Mietsache überlassen und erhalten."
        ),
        "is_hallucination_plant": False,
        "sections_needed": ["§535"],
        "collection": config.STATUTES_COLLECTION,
        "notes": "Basic landlord obligations question.",
    },
    {
        "question": (
            "Wie hoch darf die Sicherheit sein, die der Mieter dem "
            "Vermieter bei einem Wohnraummietverhältnis leisten muss?"
        ),
        "answer": (
            "Die Sicherheit darf höchstens das Dreifache der auf einen "
            "Monat entfallenden Miete ohne die als Pauschale oder als "
            "Vorauszahlung ausgewiesenen Betriebskosten betragen. "
            "Bei einem Mietverhältnis über Wohnraum ist eine zum Nachteil "
            "des Mieters abweichende Vereinbarung unwirksam."
        ),
        "ground_truth": (
            "Hat der Mieter dem Vermieter Sicherheit zu leisten, darf "
            "diese höchstens das Dreifache der auf einen Monat "
            "entfallenden Miete ohne die als Pauschale oder als "
            "Vorauszahlung ausgewiesenen Betriebskosten betragen "
            "(§551 Abs. 1 BGB)."
        ),
        "is_hallucination_plant": False,
        "sections_needed": ["§551", "§551 Abs. 1"],
        "collection": config.STATUTES_COLLECTION,
        "notes": "Kaution cap question — retrieves §551 Abs. 1.",
    },
    {
        "question": "Welche Kosten gelten nach der Betriebskostenverordnung als Betriebskosten?",
        "answer": (
            "Betriebskosten sind die Kosten, die dem Eigentümer oder "
            "Erbbauberechtigten durch das Eigentum oder Erbbaurecht am "
            "Grundstück oder durch den bestimmungsmäßigen Gebrauch des "
            "Gebäudes laufend entstehen. Nicht dazu gehören "
            "Verwaltungskosten und Instandhaltungskosten."
        ),
        "ground_truth": (
            "Betriebskosten sind die Kosten, die dem Eigentümer oder "
            "Erbbauberechtigten durch das Eigentum oder Erbbaurecht am "
            "Grundstück oder durch den bestimmungsmäßigen Gebrauch des "
            "Gebäudes, der Nebengebäude, Anlagen, Einrichtungen und des "
            "Grundstücks laufend entstehen (§ 1 Abs. 1 "
            "Betriebskostenverordnung). Nicht zu den Betriebskosten "
            "gehören die Verwaltungskosten und die Instandhaltungs- und "
            "Instandsetzungskosten (§ 2 Abs. 2 BetrkV)."
        ),
        "is_hallucination_plant": False,
        "sections_needed": ["BetrkV", "§1 BetrkV", "§2 BetrkV"],
        "collection": config.STATUTES_COLLECTION,
        "notes": "Retrieves §1 and §2 BetrkV chunks directly.",
    },
    # --- Multi-section recall questions ---
    {
        "question": (
            "Muss ein Mieter eine Modernisierungsmaßnahme des Vermieters dulden, "
            "und wann besteht ausnahmsweise keine Duldungspflicht?"
        ),
        "answer": (
            "Der Mieter hat eine Modernisierungsmaßnahme grundsätzlich "
            "zu dulden. Eine Duldungspflicht besteht nicht, wenn die "
            "Modernisierungsmaßnahme für den Mieter, seine Familie oder "
            "einen Angehörigen seines Haushalts eine Härte bedeuten würde, "
            "die auch unter Würdigung der berechtigten Interessen des "
            "Vermieters nicht zu rechtfertigen ist."
        ),
        "ground_truth": (
            "Der Mieter hat eine Modernisierungsmaßnahme zu dulden "
            "(§555d Abs. 1 BGB). Eine Duldungspflicht besteht nicht, wenn die "
            "Modernisierungsmaßnahme für den Mieter, seine Familie oder einen "
            "Angehörigen seines Haushalts eine Härte bedeuten würde, die auch "
            "unter Würdigung der berechtigten Interessen sowohl des Vermieters "
            "als auch anderer Mieter nicht zu rechtfertigen ist "
            "(§555d Abs. 2 BGB)."
        ),
        "is_hallucination_plant": False,
        "sections_needed": ["§555d", "§555d Abs. 1", "§555d Abs. 2"],
        "collection": config.STATUTES_COLLECTION,
        "notes": "Focused on §555d Duldungspflicht and Härtegründe exception.",
    },
    {
        "question": (
            "Wann ist eine ordentliche Kündigung eines "
            "Wohnraummietverhältnisses durch den Vermieter zulässig?"
        ),
        "answer": (
            "Der Vermieter kann ordentlich kündigen, wenn er ein "
            "berechtigtes Interesse an der Beendigung des Mietverhältnisses "
            "hat. Ein solches liegt insbesondere vor, wenn der Mieter seine "
            "vertraglichen Pflichten schuldhaft nicht unerheblich verletzt "
            "hat oder der Vermieter die Räume als Wohnung für sich, seine "
            "Familienangehörigen oder Angehörige seines Haushalts benötigt."
        ),
        "ground_truth": (
            "Der Vermieter kann nur kündigen, wenn er ein berechtigtes "
            "Interesse an der Beendigung des Mietverhältnisses hat "
            "(§573 Abs. 1 BGB). Ein berechtigtes Interesse liegt "
            "insbesondere vor, wenn der Mieter seine vertraglichen "
            "Pflichten schuldhaft nicht unerheblich verletzt hat oder "
            "der Vermieter die Räume als Wohnung für sich, seine "
            "Familienangehörigen oder Angehörige seines Haushalts "
            "benötigt (§573 Abs. 2 BGB)."
        ),
        "is_hallucination_plant": False,
        "sections_needed": ["§573", "§573 Abs. 1", "§573 Abs. 2"],
        "collection": config.STATUTES_COLLECTION,
        "notes": "Focused on §573 berechtigtes Interesse conditions only.",
    },
    {
        "question": (
            "Innerhalb welcher Frist muss ein Vermieter dem Mieter "
            "die Betriebskostenabrechnung mitteilen?"
        ),
        "answer": (
            "Der Vermieter muss jährlich über die Vorauszahlungen für "
            "Betriebskosten abrechnen und den Grundsatz der "
            "Wirtschaftlichkeit beachten. Die Abrechnung ist dem Mieter "
            "spätestens bis zum Ablauf des zwölften Monats nach Ende des "
            "Abrechnungszeitraums mitzuteilen. Nach Ablauf dieser Frist "
            "ist die Geltendmachung einer Nachforderung ausgeschlossen."
        ),
        "ground_truth": (
            "Über die Vorauszahlungen für Betriebskosten ist jährlich "
            "abzurechnen; dabei ist der Grundsatz der Wirtschaftlichkeit "
            "zu beachten (§556 Abs. 3 BGB). Die Abrechnung ist dem Mieter "
            "spätestens bis zum Ablauf des zwölften Monats nach Ende des "
            "Abrechnungszeitraums mitzuteilen. Nach Ablauf dieser Frist "
            "ist die Geltendmachung einer Nachforderung durch den Vermieter "
            "ausgeschlossen, es sei denn, der Vermieter hat die verspätete "
            "Geltendmachung nicht zu vertreten."
        ),
        "is_hallucination_plant": False,
        "sections_needed": ["§556", "§556 Abs. 3"],
        "collection": config.STATUTES_COLLECTION,
        "notes": "Requires chunks from §556 and §556 Abs. 3.",
    },
    # --- Planted hallucination (20%-rule misconception) ---
    {
        "question": (
            "Um wie viel Prozent darf der Vermieter die Miete im Rahmen "
            "der Mietpreisbremse über die ortsübliche Vergleichsmiete hinaus erhöhen?"
        ),
        "answer": (
            "Der Vermieter darf die Miete im Rahmen der Mietpreisbremse "
            "um bis zu 20 Prozent über die ortsübliche Vergleichsmiete hinaus erhöhen."
        ),
        "ground_truth": (
            "Die Mietpreisbremse (§556d BGB) begrenzt die zulässige Miete "
            "auf höchstens 10 Prozent über der ortsüblichen Vergleichsmiete, "
            "nicht 20 Prozent."
        ),
        "is_hallucination_plant": True,
        "sections_needed": ["§556d"],
        "collection": config.STATUTES_COLLECTION,
        "notes": (
            "Deliberately wrong answer: claims 20% premium instead of the "
            "correct 10% cap under §556d BGB (Mietpreisbremse)."
        ),
    },
    # --- Case-law questions (answerable from ingested court decisions) ---
    {
        "question": (
            "Innerhalb welcher Frist muss der Vermieter nach Ablauf der "
            "Überlegungsfrist des Mieters Klage auf Zustimmung zu einer "
            "Mieterhöhung erheben?"
        ),
        "answer": (
            "Der Mieter hat eine Überlegungsfrist bis zum Ablauf des "
            "zweiten Kalendermonats nach Zugang des Mieterhöhungsverlangens. "
            "Stimmt der Mieter nicht zu, kann der Vermieter innerhalb von "
            "drei weiteren Monaten nach Ablauf der Überlegungsfrist auf "
            "Zustimmung klagen."
        ),
        "ground_truth": (
            "Der Vermieter kann auf Erteilung der Zustimmung nur bis zum "
            "Ablauf des dritten Kalendermonats nach dem Ende der "
            "Überlegungsfrist des Mieters klagen (§558b Abs. 2 BGB); diese "
            "Klagefrist wurde vom BGH (Urteil vom 29.04.2020, VIII ZR "
            "355/18) als Voraussetzung der Begründetheit der "
            "Zustimmungsklage eingeordnet."
        ),
        "is_hallucination_plant": False,
        "sections_needed": ["§558b", "§558b Abs. 2"],
        "collection": config.CASE_LAW_COLLECTION,
        "notes": "BGH VIII ZR 355/18 — Überlegungs- und Klagefrist nach §558b Abs. 2 BGB.",
    },
    {
        "question": (
            "Wird die Mietminderung bei einem Mangel, der nur eine "
            "mitvermietete Garage betrifft, anhand der Garagenmiete oder "
            "anhand der gesamten Bruttomiete berechnet?"
        ),
        "answer": (
            "Die Minderung wird anhand der gesamten einheitlichen "
            "Bruttomiete berechnet, nicht nur anhand des auf die Garage "
            "entfallenden Mietanteils."
        ),
        "ground_truth": (
            "Die Minderung berechnet sich grundsätzlich nach der "
            "einheitlichen Bruttomiete; die einheitliche Gebrauchsgewähr "
            "des Vermieters darf nicht in Teilleistungen zerlegt werden — "
            "auch wenn der Mangel nur die mitvermietete Garage betrifft "
            "(LG Bonn, Urteil vom 12.11.2015)."
        ),
        "is_hallucination_plant": False,
        "sections_needed": ["§536"],
        "collection": config.CASE_LAW_COLLECTION,
        "notes": "LG Bonn 2015-11-12 — Mietminderung bei Mangel an mitvermieteter Garage.",
    },
    # --- Additional statute questions (broaden coverage of the primary corpus) ---
    {
        "question": (
            "Unter welchen Voraussetzungen kann ein Mietverhältnis außerordentlich "
            "fristlos aus wichtigem Grund gekündigt werden?"
        ),
        "answer": (
            "Jede Vertragspartei kann das Mietverhältnis aus wichtigem Grund "
            "außerordentlich fristlos kündigen. Ein wichtiger Grund liegt vor, wenn "
            "dem Kündigenden unter Berücksichtigung aller Umstände des Einzelfalls "
            "und unter Abwägung der beiderseitigen Interessen die Fortsetzung des "
            "Mietverhältnisses bis zum Ablauf der Kündigungsfrist nicht zugemutet "
            "werden kann."
        ),
        "ground_truth": (
            "Jede Vertragspartei kann das Mietverhältnis aus wichtigem Grund "
            "außerordentlich fristlos kündigen. Ein wichtiger Grund liegt vor, wenn "
            "dem Kündigenden unter Berücksichtigung aller Umstände des Einzelfalls, "
            "insbesondere eines Verschuldens der Vertragsparteien, und unter Abwägung "
            "der beiderseitigen Interessen die Fortsetzung des Mietverhältnisses bis "
            "zum Ablauf der Kündigungsfrist nicht zugemutet werden kann "
            "(§543 Abs. 1 BGB)."
        ),
        "is_hallucination_plant": False,
        "sections_needed": ["§543", "§543 Abs. 1"],
        "collection": config.STATUTES_COLLECTION,
        "notes": "Fristlose Kündigung aus wichtigem Grund — §543 Abs. 1 BGB.",
    },
    {
        "question": (
            "Welche Kündigungsfrist gilt bei der ordentlichen Kündigung von Wohnraum "
            "und wie verlängert sie sich für den Vermieter mit der Mietdauer?"
        ),
        "answer": (
            "Die Kündigung ist spätestens am dritten Werktag eines Kalendermonats "
            "zum Ablauf des übernächsten Monats zulässig. Für den Vermieter "
            "verlängert sich die Frist nach fünf und acht Jahren seit Überlassung "
            "des Wohnraums um jeweils drei Monate."
        ),
        "ground_truth": (
            "Die Kündigung ist spätestens am dritten Werktag eines Kalendermonats "
            "zum Ablauf des übernächsten Monats zulässig. Die Kündigungsfrist für "
            "den Vermieter verlängert sich nach fünf und acht Jahren seit der "
            "Überlassung des Wohnraums um jeweils drei Monate (§573c Abs. 1 BGB)."
        ),
        "is_hallucination_plant": False,
        "sections_needed": ["§573c", "§573c Abs. 1"],
        "collection": config.STATUTES_COLLECTION,
        "notes": "Ordentliche Kündigungsfristen — §573c Abs. 1 BGB.",
    },
    {
        "question": "Welche Auswirkung hat ein Mangel der Mietsache auf die Miete nach § 536 BGB?",
        "answer": (
            "Hebt ein Mangel die Tauglichkeit der Mietsache zum vertragsgemäßen "
            "Gebrauch auf, ist der Mieter für diese Zeit von der Miete befreit; ist "
            "die Tauglichkeit nur gemindert, hat er eine angemessen herabgesetzte "
            "Miete zu entrichten. Eine unerhebliche Minderung bleibt außer Betracht."
        ),
        "ground_truth": (
            "Hat die Mietsache einen Mangel, der ihre Tauglichkeit zum "
            "vertragsgemäßen Gebrauch aufhebt, ist der Mieter für die Zeit der "
            "Aufhebung von der Entrichtung der Miete befreit; für die Zeit einer "
            "Minderung der Tauglichkeit hat er nur eine angemessen herabgesetzte "
            "Miete zu entrichten. Eine unerhebliche Minderung der Tauglichkeit bleibt "
            "außer Betracht (§536 Abs. 1 BGB)."
        ),
        "is_hallucination_plant": False,
        "sections_needed": ["§536", "§536 Abs. 1"],
        "collection": config.STATUTES_COLLECTION,
        "notes": "Mietminderung bei Mangel — §536 Abs. 1 BGB.",
    },
    {
        "question": (
            "Ist eine formularmäßige Übertragung der Schönheitsreparaturen auf den "
            "Mieter wirksam, wenn ihm die Wohnung unrenoviert übergeben wurde?"
        ),
        "answer": (
            "Nein. Eine Formularklausel, die dem Mieter die Schönheitsreparaturen "
            "auferlegt, ist unwirksam, wenn ihm die Wohnung unrenoviert übergeben "
            "wurde und er dafür keinen angemessenen Ausgleich erhält."
        ),
        "ground_truth": (
            "Eine formularvertragliche Übertragung der Schönheitsreparaturen auf den "
            "Mieter ist unwirksam, wenn die Wohnung dem Mieter bei Mietbeginn "
            "unrenoviert überlassen wurde und der Mieter dafür keinen angemessenen "
            "Ausgleich erhält, weil er sonst zur Beseitigung auch vom Vormieter "
            "stammender Gebrauchsspuren verpflichtet würde (BGH, Urteil vom "
            "18.03.2015, VIII ZR 21/13)."
        ),
        "is_hallucination_plant": False,
        "sections_needed": ["§535"],
        "collection": config.CASE_LAW_COLLECTION,
        "notes": "BGH VIII ZR 21/13 — Schönheitsreparaturen bei unrenoviert übergebener Wohnung.",
    },
]
