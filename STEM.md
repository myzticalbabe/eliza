# STEM learning guide — eliza

ELIZA is a companion runtime: a small therapeutic conversation loop built on shards — units adopted from the wider tree — with an explicit ethical boundary around what it will and will not claim to be.

This guide is for teachers, mentors, club leaders, parents and students who want to
use this repository as a vehicle for real STEM learning — in particular for girls and
other groups still under-represented in computing, engineering and mathematics. It
says what the project actually teaches, how to run a session with it, and what to
remove so that nobody is excluded by accident.

## What this project teaches

**Subject areas**

- state machines
- graph modelling
- conversational interfaces
- ethics of automated advice

**Skills practised**

- modelling a conversation as states and transitions
- writing a test for behaviour, not for wording
- recognising where a system must refuse

## Prerequisites

Python 3.10 or newer. No machine-learning background: the loop is deterministic arithmetic and rules, deliberately.

Nothing else is assumed for the entry-level activity below: no prior programming
experience, no particular hardware, and no home internet connection.

## Six practices this repository is set up to support

These follow the published guidance on gender-equitable STEM education — connect the
work to learners' lives, let them investigate real problems, treat struggle as part of
the work, name and challenge stereotypes, make the work collaborative, and put
learners in front of diverse role models.

1. **Connect it to their lives.** chatbots learners already talk to, and the question of when one should say 'I don't know' instead of guessing
2. **Let them investigate.** ask the group to write a conversation the system must refuse, then find whether it actually does
3. **Make struggle normal.** Build the session so that the first attempt is *expected*
   to fail. Say out loud that debugging is the subject, not a penalty. Ask "what did
   that error tell you?" before offering the answer.
4. **Challenge the stereotype.** Name who does this work and why it is not a gendered
   skill. Praise the method ("you isolated the variable"), not the person ("you're a
   natural") — the second kind of praise teaches learners that ability is fixed.
5. **Make it social.** pairs write a dialogue and swap it; the receiving pair has to state what the system believed at each turn
6. **Show diverse role models.** researchers in human-computer interaction and clinical informatics, and critics of automated therapy

## A 90-minute session

1. *(15 min)* Draw the state machine from the code, on paper.
2. *(25 min)* Write a dialogue that should trigger a refusal.
3. *(35 min)* Add the missing guardrail and a test for it.
4. *(15 min)* Discuss: what should this never be used for?

## Vocabulary to define before the session

Specialist vocabulary is a hidden entry test if nobody explains it. Define each of
these the first time it appears, in one sentence, in the learners' own words:

1. **state** — what the system currently believes.
2. **transition** — the rule that moves between states.
3. **shard** — an adopted, self-contained unit of behaviour.
4. **guardrail** — a refusal the system must not cross.

## Accessibility

Read [ACCESSIBILITY.md](ACCESSIBILITY.md) before running a session. Two rules matter
most in a mixed-ability room:

- Every activity must be completable with a keyboard alone, with a visible focus ring.
- Every instruction names the control or the heading ("the **Run** button in the
  toolbar"), never a colour or a position.

Pair learners rather than singling anyone out, and always offer a text-only route for
a visual step.

## Contributing as a learner

Small, well-scoped contributions are the point, not a consolation prize:

- Browse issues labelled
  [`good first issue`](https://github.com/myzticalbabe/eliza/labels/good%20first%20issue).
- Read [CONTRIBUTING.md](CONTRIBUTING.md) — it has a section written for first-time
  contributors.
- Ask in [SUPPORT.md](SUPPORT.md) if anything is unclear. Asking is expected here; it
  is not a failure.

## Licence and classroom reuse

Classroom, club and workshop use is welcome. See `LICENSE` for the exact terms, and
check whether your institution requires a separate agreement before redistributing
modified copies.
