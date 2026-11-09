"""The fixed sentences of ``meaning/interview.md``, shared by the writer (``docs.interview_md``) and the reader
(``intent.py``), so a user who copies the interview into ``meaning/intent.md`` never turns the harness's own text into
their notes (UD1). Stdlib only."""
from __future__ import annotations

import re

__all__ = ["OBEY", "PREAMBLE", "TEMPLATE_HEADING", "TEMPLATE_INTRO", "NEVER_SHOW_Q", "QUESTIONS", "PLAIN_QUESTIONS",
           "ECHO_LINE", "VOICE_FACT", "WHICH_CHARACTER", "OPEN_QUESTIONS_HEADING"]

#: the one sentence UD1 asks every user-facing document to say plainly
OBEY = "Anything that must be obeyed goes in the template."

PREAMBLE = ("The harness found the facts below. **You are the authority on what the song means.** Answer in "
            "`meaning/intent.md`, in two ways. **" + OBEY + "** The template at the end holds the characters, "
            "which voice each one sings, each section's feel, meaning, movement, camera and palette, and the do-not "
            "rules (the only hard constraints). Everything else can be free text: every agent reads it as your own "
            "notes, word for word, but never as a rule or a field. `mvh analyze` never edits that file. An agent may "
            "draft the gaps into `meaning/authored.json` only after you have seen these questions; your answers always "
            "win over its draft.")
TEMPLATE_HEADING = "## Template (copy into meaning/intent.md)"
TEMPLATE_INTRO = ("Copy the block below into `meaning/intent.md` (with or without the fence) and fill in what you want "
                  "obeyed. Empty = no answer. Free text outside the block stays your notes.")
NEVER_SHOW_Q = ("what must never appear on screen? Write each rule under `do_not` in the template (copied verbatim to "
                "every agent); free text is never a rule.")
OPEN_QUESTIONS_HEADING = "## Open questions"

#: (bold question title, regex of the harness's text after the title). Old wordings stay accepted.
QUESTIONS: tuple[tuple[str, str], ...] = (
    (r"What does this song mean to you\?",
     r"One sentence \(the logline\), then as much as you like\.(?:\s*Credits found: .*?\)\.)?"),
    (r"Who sings to whom\?", r"\d+ voice\(s\) were found\b.*?lane\):"),
    (r"Check the singer", r"of \d+ low-confidence line\(s\).*?under `line_singers`\."),
    (r"The hooks", r"repeat:\s*\S+ \(\d+x:.*?Should they look the same each time\?"),
    (r"The world", r":\s*where and when does the video take place\?(?:\s*Who are the characters "
                   r"\(look, age, costume\)\?)?(?:\s*Any visual references \(films, artists, photos\)\?)?"),
    (r"The mood arc", r"the audio models hear\b.*?Where should it differ\?"),
    (r"How should each section feel and move\?", r"Sections:.*?For each: feel, what it means, movement/choreography, camera\."
                                                 r"(?:\s*Put them under `sections` in the template\.)?"),
    (r"The top moments", r":\s*#\d+ \d+:\d.*?What should happen on screen at each\?"),
    (r"Colours", r":\s*which palette belongs to the song\b[^?]*\?(?:\s*Per-section colours\?)?"
                 r"(?:\s*\(template: `palette`, `sections\.\*\.palette`\))?"),
    (r"Never show", r":\s*what must never appear on screen\?(?:\s*\(copied verbatim to every agent\))?"
                    r"(?:\s*Write each rule under `do_not` in the template \(copied verbatim to every agent\); free text is "
                    r"never a rule\.)?"),
)
#: unbolded questions (the whole question is harness text)
PLAIN_QUESTIONS: tuple[str, ...] = (
    r"The song is \*\*instrumental\*\* \(no lyrics were found\)\. What story or image should carry it\?",
    r"No lyrics were found\. Are there words to show\?(?: \(pass `--lyrics`[^)]*\))?",
    r"No separate voices were detected\. Is it one singer throughout\?(?: If not, who sings which lines\?)?",
)
#: whole interview lines that are the harness's (never notes)
ECHO_LINE = re.compile(
    r"^[ \t]*(?:#[ \t]+Interview:.*|#[ \t]+What this song means to me \(meaning/intent\.md\)"
    r"|The harness found the facts below\..*|Current meaning status: \*\*\w+\*\*.*"
    r"|Already answered in intent\.md:.*|" + re.escape(TEMPLATE_HEADING) + r"[ \t]*|" + re.escape(TEMPLATE_INTRO)
    + r"[ \t]*)$")
#: a voice-fact bullet, as interview_md writes it; text after it is the user's
VOICE_FACT = re.compile(
    r"^[ \t]*(?:[-*][ \t]+)?\*\*(V\d+)\*\*: \d+(?:\.\d+)? s, \d+ lines(?:, first heard at \d+:\d+(?:\.\d)? \(L\d+\))?"
    r"(?:, sections S\d+(?:, S\d+)*)?(?:; the lyrics label it '[^']*')?(?:; now mapped to C\d+ \(.*, (?:user|draft)\))?")
#: the line after the voice facts; text after it is the user's
WHICH_CHARACTER = re.compile(r"^[ \t]*Which character is each voice\? Is any voice a narrator or announcer"
                             r"(?: \(rap battles often open with one\))?\?(?: Map them in the template \(`characters` "
                             r"or `voices`\)\.)?")
