# Dynamic Arabic Learning App: Vision, Pedagogical Method & Counterfactual Sandbox Architecture

## 1. Core Purpose & The Problem With Existing Arabic Apps

Most language learning applications fail at teaching Arabic because they treat it like a European concatenative language: static flashcards, memorized surface strings, and rigid string-matching exercises where a student is shown a red "X" without ever understanding *why* their inflection or word order failed—or worse, without realizing their sentence was actually grammatically valid but meant something completely different.

Arabic is an algebraic, non-concatenative language governed by two interlocking systems:
1. **Al-Ṣarf (Morphology):** Words are compiled by slotting a 3- or 4-consonant semantic root (*Jadhr*, e.g., `ك-ت-ب`) into a vocalized pattern template (*Wazn*, e.g., `فَاعِل` / `1َا2ِ3`), applying deterministic morphophonemic weak-root laws (*Iʿlāl* and *Ibdāl*), and attaching proclitics, stem tails, and enclitics.
2. **Al-Naḥw (Syntax & Case Government):** Word order is flexible, and semantic roles (who acted vs. who was acted upon) are governed by syntactic operators (*ʿAwāmil*) that assign terminal case endings (*Iʿrāb*: *Marfūʿ* `ـُ`, *Manṣūb* `ـَ`, *Majrūr* `ـِ`, *Majzūm* `ـْ`).

**Core Goal of This Application:**
To build a dynamic, state-tracked Arabic learning platform powered by a neuro-symbolic morphological and syntactic brain (`arabic-root-tree`). Instead of memorizing flat vocabulary lists, the user unlocks **generative grammatical coordinates** `(Roots × Patterns × Syntactic Rules)` and masters them through a **Counterfactual Sentence Sandbox** where every change in word placement, template, or terminal diacritic dynamically recomputes grammatical validity, syntactic government arrows, and exact semantic translation in real time.

---

## 2. The Core Learning Loop (4-Stage Pedagogical State Machine)

### Stage 1: Guided Structural Lesson (*Taʿlīm*)
Each lesson introduces a bounded set of new nodes across three axes:
- **Lexical Roots (*Judhūr*):** 3 to 5 new roots (e.g., `ن-ص-ر` "to help", `ع-ل-م` "to know", `ق-و-ل` "to say").
- **Morphological Patterns (*Awzān* & *Lawāḥiq*):** 1 to 2 templates or suffixes (e.g., Form I Past Active `فَعَلَ` vs. Passive `فُعِلَ`, Active Participle `فَاعِل`, Sound Masculine Plural `ـُونَ / ـِينَ`).
- **Syntactic Conditions (*Qawāʿid al-Naḥw*):** 1 governing rule (e.g., *Al-Fāʿil* is always *Marfūʿ* with *ḍammah* `ـُ` or `ـُونَ`; *Al-Mafʿūl bihi* is always *Manṣūb* with *fatḥah* `ـَ` or `ـِينَ`; a noun after *Ḥarf Jarr* is *Majrūr* with *kasrah* `ـِ`).

Every word presented in the lesson is clickable, exposing its live structural decomposition from the backend engine:
- **Root & Root Class:** Sound (*Ṣaḥīḥ*), Hollow (*Ajwaf*), Defective (*Nāqiṣ*), Geminate (*Muḍaʿʿaf*), or Hamzated (*Mahmūz*).
- **Mīzān Ṣarfī:** Exact template mapping (`1َ2َ3` $\to$ `فَعَلَ`) and *Iʿlāl* step-by-step transformation trace (e.g., `قَوَلْتُ` $\to$ `قُلْتُ` via medial weak-radical deletion before a consonant suffix).
- **Iʿrāb & Governor Link:** Visual arrow pointing from the governed word (*Maʿmūl*) to the governing word (*ʿĀmil*) that caused its ending vowel.

---

### Stage 2: Mastery Assessment Gate (*Ikhtibār*)
To advance from Lesson $N$ to Lesson $N+1$, the user must pass a verification gate testing their active command of the current lesson's nodes combined with previously unlocked nodes.
- Assessments are ** pure decision tasks** (Choice / Score / Construction—never free-form English guessing):
  1. **Diacritic Decision:** Given an unvocalized target word in context, select the exact vocalization and terminal *Iʿrāb* vowel.
  2. **Morphological Compilation:** Given a root and target meaning in a sentence, select or dial the exact *Wazn* and suffix (`مُقَدِّمَاتٍ` vs. `مُتَقَدِّمُونَ`).
  3. **Role Identification:** Identify the *Fāʿil*, *Mafʿūl bihi*, or *Muḍāf ilayhi* when word order is inverted (`V-O-S` vs. `V-S-O`).

---

### Stage 3: The Progression Lock & Remediation Trigger
The backend tracks mastery at the **coordinate level**, not the surface-word level.
- Every user interaction updates a per-node Bayesian/Elo mastery score in `user_knowledge.sqlite` across:
  - `root_mastery(user_id, root_id)`
  - `pattern_mastery(user_id, wazan_id, tail_id)`
  - `nahw_mastery(user_id, rule_id)`
- **Lock Condition:** If a user's mastery score on any required node in Lesson $N$ falls below the progression threshold ($\tau_{\text{pass}} = 0.85$) or fails $\ge 2$ consecutive checks, **Lesson $N+1$ remains locked**.
- Instead of repeating the same static quiz question, the app automatically transitions the user into **Stage 4: The Freestyle Counterfactual Sandbox**, seeded specifically with the locked vocabulary/grammar node and their already-mastered vocabulary.

---

### Stage 4: Freestyle Counterfactual Sentence Sandbox (*Al-Mukhtabar*)
When a user is stuck on a vocabulary root, pattern, or *Iʿrāb* rule, they enter an interactive sentence-rebuilding workspace constrained exclusively to their unlocked vocabulary pool plus the locked target items.

#### How the Sandbox UI Works:
1. **Draggable Word/Root Tiles:** Users arrange and reorder tiles freely in the sentence tray (e.g., moving a noun before or after a verb, or moving a prepositional phrase).
2. **Morphology Dial per Tile:** Users can mutate a tile's *Wazn* (e.g., switching `نَصَرَ` Active Past $\leftrightarrow$ `نُصِرَ` Passive Past $\leftrightarrow$ `نَاصِرٌ` Active Participle), toggle definiteness (`الـ` vs. indefinite *tanwīn*), and attach proclitics (`بِـ`, `لِـ`, `وَ`) or plural tails (`ـُونَ`, `ـِينَ`, `ـَات`). The backend compiler (`render_triple`) renders the stem consonantal and internal vowel changes deterministically.
3. **Terminal *Iʿrāb* Diacritic Selector:** Users explicitly set the final diacritic on each word (`ـُ`, `ـٌ`, `ـَ`, `ـً`, `ـِ`, `ـٍ`, `ـْ`).

#### How the Sandbox Brain Responds in Real Time:
Every time the user moves a tile or flips a single diacritic, the backend evaluates the new sequence in `< 10 ms` and classifies the result into one of **two distinct pedagogical states**:

##### State A: Valid Grammatical Mutation (Meaning Shifts Dynamically!)
If the user's new arrangement or diacritic change produces a grammatically legal Arabic sentence, the engine **does not mark it wrong**—it shows how that exact change altered the meaning of the sentence:
- **Example 1 — Terminal Vowel Flip on Nouns:**
  - User builds: `نَصَرَ المُسْلِمُ الرَّجُلَ` (`NOM` then `ACC`)
    - **Engine Output:** ✅ Valid Verbal Sentence. *Fāʿil* (Doer) = `المُسْلِمُ` (`ـُ`). *Mafʿūl bihi* (Receiver) = `الرَّجُلَ` (`ـَ`).
    - **Live Translation:** *"The Muslim helped the man."*
  - User flips only the last vowels: `نَصَرَ المُسْلِمَ الرَّجُلُ` (`ACC` then `NOM`)
    - **Engine Output:** ✅ Valid Verbal Sentence (Fronted Object / *Mafʿūl bihi Muqaddam*). Because `المُسْلِمَ` now carries *fatḥah* (`ـَ`), it is the receiver even though it stands right next to the verb! Because `الرَّجُلُ` carries *ḍammah* (`ـُ`), the man is now the doer!
    - **Live Translation:** *"The man helped the Muslim."*
- **Example 2 — Internal Vowel Flip on the Verb (Voice Mutation):**
  - User changes `نَصَرَ المُسْلِمُ` to `نُصِرَ المُسْلِمُ` (`1َ2َ3َ` $\to$ `1ُ2ِ3َ`):
    - **Engine Output:** ✅ Valid Passive Verbal Sentence (*Mabnī lil-Majhūl*). `المُسْلِمُ` shifts from *Fāʿil* (Doer) to *Nāʾib al-Fāʿil* (Deputy Subject—the one who was helped), while keeping its *ḍammah* (`ـُ`)!
    - **Live Translation:** *"The Muslim was helped."*
- **Example 3 — Word Order Shift (`VSO` $\to$ `SVO` Nominal Clause):**
  - User drags `المُسْلِمُونَ` before the verb:
    - `نَصَرَ المُسْلِمُونَ الرَّجُلَ` (Singular verb before plural *Fāʿil*) $\to$ ✅ Valid (`VSO` rule: verb stays singular when preceding a plural subject).
    - `المُسْلِمُونَ نَصَرُوا الرَّجُلَ` (Noun fronted as *Mubtadaʾ*) $\to$ ✅ Valid Nominal Sentence (*Jumlah Ismiyyah*: verb must now carry plural `ـُوا` to agree with the fronted *Mubtadaʾ*).

##### State B: Grammatical or Morphological Violation (Exact Diagnostic Feedback)
If the user's tile placement or diacritic choice violates Arabic grammar, the engine pinpoints the exact broken constraint AND shows the broken literal meaning so the user understands *why* the rule exists:
- **Violation 1 — Role Collision (`Double NOM` or `Double ACC`):**
  - User builds: `نَصَرَ المُسْلِمَ الرَّجُلَ` (both nouns given *fatḥah* `ـَ`).
  - **Engine Output:** 🔴 **Missing Doer (*Fāʿil*):** Both `المُسْلِمَ` and `الرَّجُلَ` are marked with *fatḥah* (`ـَ`) as objects (*Mafʿūl bihi*). Every active verb requires a doer marked with *ḍammah* (`ـُ`).
  - **Broken Meaning Preview:** *"Helped [??? — no doer!] the Muslim, the man."*
- **Violation 2 — Preposition Government Breach (*Jār wa-Majrūr*):**
  - User builds: `ذَهَبَ الرَّجُلُ إِلَى المَسْجِدُ` (`NOM` after `إِلَى`).
  - **Engine Output:** 🔴 **Governor Violation:** The particle `إِلَى` is a *Ḥarf Jarr* (preposition). It governs the noun after it and forces its ending into *Jarr* (*kasrah* `ـِ`), never *ḍammah* (`ـُ`). Correction: `المَسْجِدِ`.
- **Violation 3 — Definiteness + *Tanwīn* Clash:**
  - User puts `ـٌ` (*tanwīn*) on `الرَّجُل`: `الرَّجُلٌ`.
  - **Engine Output:** 🔴 **Morphological Clash:** The prefix `الـ` ("the") makes a noun definite, while *tanwīn* (`ـٌ`) marks it indefinite ("a"). A word cannot be both "the man" and "a man" at the same time. Use `الرَّجُلُ` or `رَجُلٌ`.
- **Violation 4 — Agreement Mismatch (`VSO` vs. `SVO` or Gender):**
  - User builds: `المُسْلِمُونَ نَصَرَ الرَّجُلَ` (Fronted plural subject with singular verb).
  - **Engine Output:** 🔴 **Agreement Error:** When the plural subject `المُسْلِمُونَ` comes *before* the verb, the verb must carry the plural pronoun suffix `ـُوا` (`نَصَرُوا`).

#### Unlocking Progression from the Sandbox:
To exit the Sandbox and unlock the next lesson, the user must successfully complete **3 Counterfactual Challenges** using the locked vocabulary item (e.g., *"Use `المُسْلِم` once as the Doer (*Fāʿil*), once as the Receiver (*Mafʿūl bihi*) with fronted word order, and once governed by a preposition"*).

---

## 3. Data Schema for the Knowledge Graph & Curriculum (`user_knowledge.sqlite`)

```sql
CREATE TABLE curriculum_roots (
    root_id TEXT PRIMARY KEY,          -- e.g. 'نصر'
    radicals_json TEXT NOT NULL,       -- '["ن","ص","ر"]'
    root_class TEXT NOT NULL,          -- 'sound' | 'hollow_waw' | 'hollow_ya' | 'defective' | 'geminate' | 'hamzated'
    core_meaning_en TEXT NOT NULL,     -- 'helping / supporting'
    core_meaning_id TEXT,              -- Indonesian gloss
    lesson_unlock_order INTEGER NOT NULL
);

CREATE TABLE curriculum_lemmas (
    lemma_id TEXT PRIMARY KEY,         -- e.g. 'نصر_1َ2َ3َ'
    root_id TEXT NOT NULL REFERENCES curriculum_roots(root_id),
    wazan_stem TEXT NOT NULL,          -- '1َ2َ3'
    mizan_label TEXT NOT NULL,         -- 'فَعَلَ (Form I Past Active)'
    upos TEXT NOT NULL,                -- 'VERB' | 'NOUN' | 'ADJ'
    valency TEXT NOT NULL,             -- 'INTRANSITIVE' | 'TRANSITIVE' | 'DITRANSITIVE' | 'COPULAR'
    en_gloss_template TEXT NOT NULL    -- '{agent} helped {patient}'
);

CREATE TABLE user_node_mastery (
    user_id TEXT NOT NULL,
    node_type TEXT NOT NULL,           -- 'ROOT' | 'WAZAN' | 'TAIL' | 'NAHW_RULE'
    node_id TEXT NOT NULL,
    mastery_prob REAL NOT NULL DEFAULT 0.0,
    consecutive_correct INTEGER NOT NULL DEFAULT 0,
    consecutive_wrong INTEGER NOT NULL DEFAULT 0,
    is_locked_remediation INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, node_type, node_id)
);