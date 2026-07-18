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
    # --- Additional case-law questions (expand the case-law eval set to n=20 so the
    # case-law retrieval metrics are statistically meaningful; each item is grounded
    # in a decision present in the ingested corpus, cited in `notes`). ---
    {
        "question": (
            "Ist eine formularmäßige Quotenabgeltungsklausel für Schönheitsreparaturen "
            "wirksam, und was folgt aus ihrer Unwirksamkeit für die übrigen "
            "Schönheitsreparaturklauseln im Mietvertrag?"
        ),
        "answer": (
            "Eine formularmäßige Quotenabgeltungsklausel ist unwirksam. Nach dem "
            "Prinzip der Gesamtinfektion erfasst die Unwirksamkeit einer "
            "Schönheitsreparaturklausel die gesamte Überbürdung der "
            "Schönheitsreparaturen auf den Mieter."
        ),
        "ground_truth": (
            "Die Quotenabgeltungsklausel ist unwirksam. Wegen des Verbots der "
            "geltungserhaltenden Reduktion und des Prinzips der Gesamtinfektion "
            "schlägt die Unwirksamkeit auf die gesamte formularmäßige Überbürdung "
            "der Schönheitsreparaturen durch, sodass diese insgesamt unwirksam ist "
            "(AG Blomberg, Urteil vom 24.01.2023, 4 C 111/22)."
        ),
        "is_hallucination_plant": False,
        "sections_needed": ["§535", "§307"],
        "collection": config.CASE_LAW_COLLECTION,
        "notes": "AG Blomberg 4 C 111/22 — Quotenabgeltungsklausel / Gesamtinfektion.",
    },
    {
        "question": (
            "Gilt die einjährige Abrechnungsfrist mit Ausschlusswirkung für "
            "Betriebskosten (§556 Abs. 3 BGB) auch für die Gewerberaummiete?"
        ),
        "answer": (
            "Nein. Die Ausschlussfrist des §556 Abs. 3 Satz 3 BGB gilt nur für die "
            "Wohnraummiete, nicht für die Gewerberaummiete."
        ),
        "ground_truth": (
            "Die Ausschlussfrist des §556 Abs. 3 Satz 3 BGB findet bei der "
            "Gewerberaummiete keine Anwendung; ebenso wenig gilt die "
            "Einwendungsausschlussfrist des §556 Abs. 3 Satz 6 BGB, da diese "
            "Vorschriften nur auf die Wohnraummiete anwendbar sind (BGH, Urteil vom "
            "28.05.2014, XII ZR 6/13)."
        ),
        "is_hallucination_plant": False,
        "sections_needed": ["§556", "§556 Abs. 3"],
        "collection": config.CASE_LAW_COLLECTION,
        "notes": "BGH XII ZR 6/13 — Ausschlussfrist §556 Abs. 3 BGB nur bei Wohnraum.",
    },
    {
        "question": (
            "Innerhalb welcher Frist muss der Vermieter nach Beendigung des "
            "Mietverhältnisses über die Kaution abrechnen, und darf er einen Teil "
            "wegen einer noch ausstehenden Betriebskostenabrechnung einbehalten?"
        ),
        "answer": (
            "Dem Vermieter steht eine angemessene Prüfungsfrist zu, die regelmäßig "
            "mit etwa sechs Monaten bemessen wird. Er darf einen angemessenen Teil "
            "der Kaution zur Sicherung einer Nachforderung aus einer noch zu "
            "erstellenden Betriebskostenabrechnung einbehalten."
        ),
        "ground_truth": (
            "Der Kautionsrückzahlungsanspruch wird nach Ablauf einer angemessenen "
            "Prüfungsfrist fällig, die nach der Rechtsprechung mit etwa sechs "
            "Monaten zu bemessen ist; der Vermieter darf einen Teil der Kaution zur "
            "Sicherung einer Nachforderung aus einer noch zu erstellenden "
            "Betriebskostenabrechnung einbehalten (AG Neuss, Urteil vom 12.07.1991, "
            "36 C 122/91)."
        ),
        "is_hallucination_plant": False,
        "sections_needed": ["§551"],
        "collection": config.CASE_LAW_COLLECTION,
        "notes": "AG Neuss 36 C 122/91 — Kaution: Prüfungsfrist ~6 Monate, Einbehalt für BK.",
    },
    {
        "question": (
            "Heilt eine Schonfristzahlung nach §569 Abs. 3 Nr. 2 BGB auch eine "
            "hilfsweise ausgesprochene ordentliche Kündigung wegen Zahlungsverzugs?"
        ),
        "answer": (
            "Grundsätzlich nein. Die Schonfristzahlung beseitigt nur die "
            "außerordentliche fristlose Kündigung, nicht die hilfsweise erklärte "
            "ordentliche Kündigung."
        ),
        "ground_truth": (
            "Die Schonfristzahlung gemäß §569 Abs. 3 Nr. 2 BGB erfasst grundsätzlich "
            "nur die außerordentliche Kündigung wegen Zahlungsverzugs, nicht die "
            "hilfsweise ausgesprochene ordentliche Kündigung; etwas anderes gilt nur "
            "ausnahmsweise nach Treu und Glauben (§242 BGB) bei besonderen Umständen "
            "(AG Tempelhof-Kreuzberg, Urteil vom 23.10.2019, 15 C 83/19)."
        ),
        "is_hallucination_plant": False,
        "sections_needed": ["§569", "§569 Abs. 3", "§543"],
        "collection": config.CASE_LAW_COLLECTION,
        "notes": "AG Tempelhof-Kreuzberg 15 C 83/19 — Schonfristzahlung heilt nur die a.o. Kündigung.",
    },
    {
        "question": (
            "Wie lange im Voraus muss der Vermieter eine Modernisierungsmaßnahme "
            "ankündigen, bevor der Mieter sie dulden muss?"
        ),
        "answer": (
            "Die Modernisierung ist dem Mieter spätestens drei Monate vor ihrem "
            "Beginn in Textform anzukündigen (§555c Abs. 1 BGB)."
        ),
        "ground_truth": (
            "Die Modernisierungsankündigung hat spätestens drei Monate vor Beginn "
            "der Maßnahme zu erfolgen; diese Frist besteht seit dem "
            "Mietrechtsreformgesetz 2001 (damals §554 Abs. 3 BGB a.F., heute §555c "
            "Abs. 1 BGB) inhaltlich unverändert fort (BGH, Urteil vom 18.03.2021, "
            "VIII ZR 305/19)."
        ),
        "is_hallucination_plant": False,
        "sections_needed": ["§555c", "§555d"],
        "collection": config.CASE_LAW_COLLECTION,
        "notes": "BGH VIII ZR 305/19 — Modernisierungsankündigung: 3-Monats-Frist.",
    },
    {
        "question": (
            "Setzt der Anspruch des Mieters auf Erlaubnis zur Untervermietung nach "
            "§553 Abs. 1 BGB voraus, dass das berechtigte Interesse erst nach "
            "Abschluss des Mietvertrags entstanden ist?"
        ),
        "answer": (
            "Ja. Das berechtigte Interesse an der Untervermietung muss nach Abschluss "
            "des Mietvertrags entstanden sein; der bloße Wunsch, einen Dritten "
            "aufzunehmen, genügt nicht."
        ),
        "ground_truth": (
            "Voraussetzung des Anspruchs auf Erlaubnis zur Untervermietung nach "
            "§553 Abs. 1 BGB ist ein berechtigtes (wirtschaftliches oder "
            "persönliches) Interesse des Mieters, das erst nach Abschluss des "
            "Mietvertrags entstanden sein muss; der bloße Wunsch zur Aufnahme eines "
            "Dritten reicht nicht aus (AG München, Urteil vom 20.12.2022, "
            "411 C 10539/22)."
        ),
        "is_hallucination_plant": False,
        "sections_needed": ["§553", "§553 Abs. 1"],
        "collection": config.CASE_LAW_COLLECTION,
        "notes": "AG München 411 C 10539/22 — Untervermietung §553: Interesse nach Vertragsschluss.",
    },
    {
        "question": (
            "Ist eine Formularklausel wirksam, die dem Mieter die Haltung von Hunden "
            "und Katzen generell verbietet?"
        ),
        "answer": (
            "Nein. Ein generelles formularmäßiges Verbot der Hunde- und Katzenhaltung "
            "ohne Möglichkeit einer Interessenabwägung benachteiligt den Mieter "
            "unangemessen und ist nach §307 BGB unwirksam."
        ),
        "ground_truth": (
            "Eine Formularklausel, die die Haltung von Hunden und Katzen generell "
            "ohne jede Möglichkeit einer Interessenabwägung verbietet, benachteiligt "
            "den Mieter unangemessen und ist gemäß §307 Abs. 1, 2 BGB unwirksam; die "
            "Tierhaltung ist dann vertragsgemäßer Gebrauch i.S.d. §535 Abs. 1 BGB "
            "(AG Köln, Urteil vom 09.08.2012, 210 C 103/12)."
        ),
        "is_hallucination_plant": False,
        "sections_needed": ["§535", "§307"],
        "collection": config.CASE_LAW_COLLECTION,
        "notes": "AG Köln 210 C 103/12 — generelles Tierhaltungsverbot (Formularklausel) unwirksam.",
    },
    {
        "question": (
            "Unter welchen Voraussetzungen ist eine formularmäßige "
            "Kleinreparaturklausel wirksam?"
        ),
        "answer": (
            "Eine Kleinreparaturklausel ist nur wirksam, wenn sie gegenständlich auf "
            "dem Zugriff des Mieters häufig ausgesetzte Teile beschränkt ist und "
            "sowohl für die einzelne Reparatur als auch für einen bestimmten "
            "Zeitraum eine zumutbare Höchstgrenze enthält."
        ),
        "ground_truth": (
            "Eine Kleinreparaturklausel ist nur dann wirksam, wenn sie einerseits "
            "gegenständlich auf Teile der Mietsache beschränkt ist, die häufig dem "
            "Zugriff des Mieters ausgesetzt sind, und andererseits eine im Rahmen "
            "des Zumutbaren bestimmte Höchstgrenze enthält – sowohl je Einzelfall "
            "als auch für die Summe innerhalb eines bestimmten Zeitraums (LG Köln, "
            "Urteil vom 04.11.2004, 6 S 36/04, unter Verweis auf BGH NJW 1991, 628)."
        ),
        "is_hallucination_plant": False,
        "sections_needed": ["§535", "§307"],
        "collection": config.CASE_LAW_COLLECTION,
        "notes": "LG Köln 6 S 36/04 — Kleinreparaturklausel: Beschränkung + Höchstgrenze.",
    },
    {
        "question": (
            "Kann der Mieter Schadensersatz verlangen, wenn sich eine "
            "Eigenbedarfskündigung nachträglich als vorgeschoben herausstellt?"
        ),
        "answer": (
            "Ja. Eine vorgeschobene Eigenbedarfskündigung ist pflichtwidrig; dem "
            "Mieter stehen Schadensersatzansprüche zu, auch wenn er auf die Angaben "
            "des Vermieters vertraut und freiwillig ausgezogen ist."
        ),
        "ground_truth": (
            "Ist der Eigenbedarf vorgeschoben, ist die Kündigung pflichtwidrig und "
            "der Vermieter dem Mieter zum Schadensersatz verpflichtet (§§535, 280 "
            "Abs. 1 BGB). Die Kausalität besteht auch dann, wenn der Mieter im "
            "Vertrauen auf die Angaben des Vermieters freiwillig ausgezogen ist, "
            "ohne Anlass zu Misstrauen zu haben (LG Kassel, Urteil vom 23.11.2023, "
            "1 S 222/22)."
        ),
        "is_hallucination_plant": False,
        "sections_needed": ["§573", "§280"],
        "collection": config.CASE_LAW_COLLECTION,
        "notes": "LG Kassel 1 S 222/22 — Schadensersatz bei vorgeschobenem Eigenbedarf.",
    },
    {
        "question": (
            "Wie kann ein Mieter geltend machen, dass seine Miete gegen die "
            "Mietpreisbremse verstößt, und was ist Rechtsfolge eines Verstoßes?"
        ),
        "answer": (
            "Der Mieter kann einen Verstoß gegen die Mietpreisbremse rügen und die "
            "Feststellung der höchstzulässigen Miete verlangen; zulässig ist "
            "höchstens die ortsübliche Vergleichsmiete zuzüglich 10 Prozent."
        ),
        "ground_truth": (
            "Der Mieter kann gegenüber dem Vermieter einen Verstoß gegen die "
            "Mietpreisbremse rügen und die Feststellung der höchstzulässigen Miete "
            "begehren; diese bemisst sich nach der ortsüblichen Vergleichsmiete "
            "(z. B. anhand des Mietspiegels) zuzüglich höchstens 10 Prozent "
            "(§§556d, 556g BGB; LG Berlin, Urteil vom 07.12.2017, 67 S 218/17)."
        ),
        "is_hallucination_plant": False,
        "sections_needed": ["§556d", "§556g"],
        "collection": config.CASE_LAW_COLLECTION,
        "notes": "LG Berlin 67 S 218/17 — Mietpreisbremse: Rüge und höchstzulässige Miete.",
    },
    {
        "question": (
            "Unter welchen Voraussetzungen kann das Gericht wegen einer "
            "Suizidgefahr des Mieters Vollstreckungsschutz gegen eine "
            "Räumungsvollstreckung gewähren?"
        ),
        "answer": (
            "Bei konkreter Suizid- oder schwerer Gesundheitsgefahr kann nach §765a "
            "ZPO Räumungsschutz gewährt werden, wenn die Räumung eine mit den guten "
            "Sitten nicht zu vereinbarende Härte darstellt; die grundrechtlich "
            "geschützten Rechtsgüter Leben und Gesundheit sind zu berücksichtigen."
        ),
        "ground_truth": (
            "Nach §765a ZPO ist Räumungsschutz zu gewähren, wenn die Vollstreckung "
            "wegen einer konkreten Gefahr für Leben und Gesundheit – etwa einer "
            "ernsthaften Suizidgefahr – eine mit den guten Sitten nicht zu "
            "vereinbarende Härte darstellt; die Gerichte müssen die grundrechtlich "
            "geschützten Belange des Schuldners hinreichend würdigen (BVerfG, "
            "Beschluss vom 23.03.2023, 2 BvR 1507/22)."
        ),
        "is_hallucination_plant": False,
        "sections_needed": ["§765a ZPO"],
        "collection": config.CASE_LAW_COLLECTION,
        "notes": "BVerfG 2 BvR 1507/22 — Räumungsschutz §765a ZPO bei Suizidgefahr.",
    },
    {
        "question": (
            "Nach welchem Maßstab sind Betriebskosten umzulegen, wenn keine wirksame "
            "abweichende Vereinbarung über den Umlageschlüssel getroffen wurde?"
        ),
        "answer": (
            "Fehlt eine wirksame abweichende Vereinbarung, sind die Betriebskosten "
            "nach dem Anteil der Wohnfläche umzulegen (§556a Abs. 1 Satz 1 BGB)."
        ),
        "ground_truth": (
            "Ist kein wirksamer abweichender Umlageschlüssel vereinbart, verbleibt es "
            "beim gesetzlichen Maßstab der Umlage nach dem Anteil der Wohnfläche "
            "gemäß §556a Abs. 1 Satz 1 BGB; eine unklare oder unwirksame Klausel "
            "(z. B. Umlage nach Miteigentumsanteilen) begründet keine abweichende "
            "Vereinbarung (LG Bonn, Urteil vom 15.11.2012, 6 S 25/12)."
        ),
        "is_hallucination_plant": False,
        "sections_needed": ["§556a", "§556a Abs. 1"],
        "collection": config.CASE_LAW_COLLECTION,
        "notes": "LG Bonn 6 S 25/12 — Umlageschlüssel: Wohnfläche als gesetzlicher Maßstab.",
    },
    {
        "question": (
            "Muss die Aufhebung einer Staffelmietvereinbarung – ebenso wie ihre "
            "Vereinbarung – der Schriftform genügen?"
        ),
        "answer": (
            "Nein. Das Schriftformerfordernis des §557a BGB gilt nach seinem "
            "Wortlaut nur für die Vereinbarung einer Staffelmiete, nicht für deren "
            "Aufhebung, die für den Mieter günstig ist."
        ),
        "ground_truth": (
            "§557a BGB sieht die Schriftform ausdrücklich nur für die Vereinbarung "
            "eines Staffelmietzinses vor; die für den Mieter günstige Aufhebung der "
            "Staffelmietvereinbarung unterliegt nicht der Schriftform, weil die "
            "Warnfunktion des Formerfordernisses insoweit nicht besteht (LG "
            "Osnabrück, Urteil vom 02.04.2004, 12 S 46/04)."
        ),
        "is_hallucination_plant": False,
        "sections_needed": ["§557a"],
        "collection": config.CASE_LAW_COLLECTION,
        "notes": "LG Osnabrück 12 S 46/04 — Schriftform §557a nur für Vereinbarung, nicht Aufhebung.",
    },
    {
        "question": (
            "Wer trägt die Beweislast dafür, ob die Ursache eines Mangels (z. B. "
            "Schimmel) aus dem Verantwortungsbereich des Vermieters oder des Mieters "
            "stammt?"
        ),
        "answer": (
            "Die Beweislast ist nach Verantwortungsbereichen verteilt: Der Vermieter "
            "muss beweisen, dass die Mangelursache nicht aus seinem Bereich stammt; "
            "gelingt ihm das, muss der Mieter beweisen, dass er den Mangel nicht zu "
            "vertreten hat."
        ),
        "ground_truth": (
            "Die Beweislast ist nach den beiderseitigen Verantwortungsbereichen "
            "verteilt: Der Vermieter muss darlegen und beweisen, dass die "
            "Mangelursache nicht aus seinem Pflichten- und Verantwortungsbereich, "
            "sondern aus dem Herrschafts- und Obhutsbereich des Mieters stammt; erst "
            "danach muss der Mieter beweisen, dass er den Mangel nicht zu vertreten "
            "hat (AG Saarburg, Urteil vom 12.10.2016, 5a C 191/15)."
        ),
        "is_hallucination_plant": False,
        "sections_needed": ["§536", "§535"],
        "collection": config.CASE_LAW_COLLECTION,
        "notes": "AG Saarburg 5a C 191/15 — Beweislastverteilung nach Verantwortungsbereichen.",
    },
    {
        "question": (
            "Ab welcher Abweichung der tatsächlichen von der vertraglich vereinbarten "
            "Wohnfläche liegt bei der Wohnraummiete ein zur Mietminderung "
            "berechtigender Mangel vor?"
        ),
        "answer": (
            "Ein Mangel im Sinne des §536 Abs. 1 BGB liegt vor, wenn die tatsächliche "
            "Wohnfläche mehr als 10 Prozent unter der im Mietvertrag angegebenen "
            "Fläche liegt; einer zusätzlichen Darlegung einer Gebrauchsbeeinträchtigung "
            "bedarf es dann nicht."
        ),
        "ground_truth": (
            "Bei der Wohnraummiete liegt ein zur Minderung berechtigender Mangel "
            "(§536 Abs. 1 Satz 1 BGB) vor, wenn die Wohnfläche mehr als 10 Prozent "
            "unter der im Mietvertrag angegebenen Fläche liegt; einer zusätzlichen "
            "Darlegung einer Tauglichkeitsminderung bedarf es nicht, und die Grenze "
            "gilt auch bei einer 'ca.'-Angabe (OLG Düsseldorf, Urteil vom 17.11.2011, "
            "I-24 U 56/11, st. Rspr. des BGH)."
        ),
        "is_hallucination_plant": False,
        "sections_needed": ["§536", "§536 Abs. 1"],
        "collection": config.CASE_LAW_COLLECTION,
        "notes": "OLG Düsseldorf I-24 U 56/11 — Wohnflächenabweichung > 10 % als Mangel.",
    },
    {
        "question": (
            "Ist die Kappungsgrenze des §558 Abs. 3 BGB zeitanteilig herabzusetzen, "
            "wenn das Mietverhältnis bei Wirksamwerden der Mieterhöhung noch keine "
            "drei Jahre bestanden hat?"
        ),
        "answer": (
            "Nein. Die Kappungsgrenze wird bei kürzeren Mietverhältnissen nicht "
            "zeitanteilig herabgesetzt; sie begrenzt die Steigerung über drei Jahre "
            "auf 20 (bzw. 15) Prozent, sodass auch eine einzige Erhöhung diese Grenze "
            "voll ausschöpfen darf."
        ),
        "ground_truth": (
            "Die Kappungsgrenze des §558 Abs. 3 BGB ist nicht zeitanteilig "
            "herabzusetzen, wenn das Mietverhältnis noch keine drei Jahre bestanden "
            "hat; sie begrenzt nicht die einzelne Erhöhung, sondern die Steigerung "
            "über einen Zeitraum von drei Jahren, sodass der Vermieter sie auch durch "
            "eine einzige Mieterhöhung ausschöpfen darf (LG Lübeck, Urteil vom "
            "29.06.2023, 14 S 95/22)."
        ),
        "is_hallucination_plant": False,
        "sections_needed": ["§558", "§558 Abs. 3"],
        "collection": config.CASE_LAW_COLLECTION,
        "notes": "LG Lübeck 14 S 95/22 — Kappungsgrenze §558 Abs. 3 nicht zeitanteilig.",
    },
    {
        "question": (
            "Setzt eine wirksame Eigenbedarfskündigung voraus, dass der "
            "Nutzungswunsch des Vermieters mit öffentlich-rechtlichen Vorgaben im "
            "Einklang steht?"
        ),
        "answer": (
            "Ja. Der Eigenbedarf nach §573 Abs. 2 Nr. 2 BGB erfordert einen auf "
            "vernünftige Gründe gestützten Nutzungswunsch; vernünftig ist er nur, "
            "wenn er mit öffentlich-rechtlichen Vorgaben (z. B. einer "
            "Erhaltungsverordnung) im Einklang steht."
        ),
        "ground_truth": (
            "Ein berechtigtes Interesse an der Eigenbedarfskündigung (§573 Abs. 2 "
            "Nr. 2 BGB) setzt einen auf vernünftige Gründe gestützten Nutzungswunsch "
            "voraus; wegen der Einheit der Rechtsordnung ist der Wunsch nur dann "
            "vernünftig, wenn er mit öffentlich-rechtlichen Vorgaben im Einklang "
            "steht – fehlt etwa die nach einer Erhaltungsverordnung erforderliche "
            "Genehmigung, ist die Kündigung unwirksam (LG Berlin, Urteil vom "
            "26.04.2022, 67 S 10/22)."
        ),
        "is_hallucination_plant": False,
        "sections_needed": ["§573", "§573 Abs. 2"],
        "collection": config.CASE_LAW_COLLECTION,
        "notes": "LG Berlin 67 S 10/22 — Eigenbedarf: Nutzungswunsch und öffentlich-rechtliche Vorgaben.",
    },
]

# Gold Aktenzeichen per case-law item, in dataset order — the specific decision each
# question was authored from. Used by the deterministic, judge-free retrieval metrics
# (hit-rate@k / MRR) in `src.eval.runner`, which measure whether that decision is
# retrieved and how highly it is ranked. (Note: several corpus decisions can support the
# same holding, so a "miss" here often means an equally valid ruling was surfaced
# instead — hit-rate is a floor on retrieval quality, not a ceiling.) The one date-only
# note (LG Bonn garage) is verified via the explicit exception below.
_CASE_LAW_GOLD_FILE_NUMBERS = [
    "VIII ZR 355/18",  # Überlegungs-/Klagefrist §558b
    "6 S 5/15",        # LG Bonn — Garage-Mietminderung (note is date-only)
    "VIII ZR 21/13",   # Schönheitsreparaturen, unrenoviert
    "4 C 111/22",      # Quotenabgeltungsklausel / Gesamtinfektion
    "XII ZR 6/13",     # Betriebskosten-Ausschlussfrist §556 Abs. 3
    "36 C 122/91",     # Kaution: Prüfungsfrist ~6 Monate
    "15 C 83/19",      # Schonfristzahlung §569
    "VIII ZR 305/19",  # Modernisierungsankündigung 3 Monate
    "411 C 10539/22",  # Untervermietung §553
    "210 C 103/12",    # Tierhaltungsverbot (Formularklausel) unwirksam
    "6 S 36/04",       # Kleinreparaturklausel
    "1 S 222/22",      # vorgeschobener Eigenbedarf -> Schadensersatz
    "67 S 218/17",     # Mietpreisbremse
    "2 BvR 1507/22",   # Räumungsschutz §765a ZPO
    "6 S 25/12",       # Umlageschlüssel §556a
    "12 S 46/04",      # Staffelmiete §557a Schriftform
    "5a C 191/15",     # Mietmangel-Beweislast nach Verantwortungsbereichen
    "I-24 U 56/11",    # Wohnflächenabweichung > 10 %
    "14 S 95/22",      # Kappungsgrenze §558 Abs. 3
    "67 S 10/22",      # Eigenbedarf: öffentlich-rechtliche Vorgaben
]

_case_law_items = [i for i in EVAL_DATASET if i["collection"] == config.CASE_LAW_COLLECTION]
assert len(_case_law_items) == len(_CASE_LAW_GOLD_FILE_NUMBERS), (
    "reference file-number list is out of sync with the case-law eval items"
)
for _item, _fn in zip(_case_law_items, _CASE_LAW_GOLD_FILE_NUMBERS):
    # Guard against reordering: the Aktenzeichen must appear in the item's own notes
    # (except the one date-only note, checked by its distinctive prefix).
    assert _fn in _item["notes"] or "LG Bonn 2015-11-12" in _item["notes"], (
        f"gold Aktenzeichen {_fn!r} does not match notes {_item['notes']!r}"
    )
    _item["reference_file_number"] = _fn
