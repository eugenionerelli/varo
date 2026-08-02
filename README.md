# varo

A Claude Code plugin for shipping static sites and keeping them honest.

Every static site exists twice: the copy in the folder and the copy people
load. They start identical and come apart quietly. Almost every tool checks the
folder. This one checks what is actually live, because that is the copy that
matters and the one nobody looks at.

## The four ways a site lies to you

These are not hypotheticals. Each one was found on a site that was already
online, serving real visitors, while every local check stayed green.

**An endpoint that exists in the code and answers 405 in production.** Its
folder was set aside during a move between hosts and never came back. The form
still submits. The page still says thank you. Nothing arrives, for months.

**A developer's own address hardcoded where config belongs.** Put in during
testing, never taken out. The site sends its mail perfectly, to the wrong
person.

**Security headers written for a host that does not serve the site.** The repo
was forked from a template built for a different platform. The config file is
right there in the root, it reads correctly, and the live host has never opened
it.

**A build step pointing at a folder this host never creates.** The minifier
finds zero files, reports success, exits 0. Nothing is minified and the log
says everything is fine.

Plus the one that hides best: **work committed, pushed, and never deployed**,
because the branch is not the one the host builds. Nothing is lost. Nothing is
live either.

## What you get

**A skill** that knows the hosts and their traps. Which config file belongs to
whom, why GitHub Pages silently drops folders starting with an underscore, how
to tell a deploy that succeeded from a deploy that served the old build.

**An auditor agent** that reports only what the live site confirmed. It fetches
before it claims. It reads and never writes, so pointing it at a client's site
in production is safe.

**A SessionStart hook** that says where you stand before you ask. Which host,
the public address, which branch deploys, how many commits are pushed and not
published. It reads locally and touches no network, so it costs milliseconds
and stays quiet in every session that is about something else.

That last part matters. A hook that speaks in every session is noise people
learn to skip.

## Installing

```bash
claude plugin marketplace add eugenionerelli/varo
claude plugin install varo@varo
```

Or clone it and load it for one session, which is the quickest way to see
whether you want it:

```bash
git clone https://github.com/eugenionerelli/varo.git
claude --plugin-dir ./varo
```

Nothing to build, and no dependency past Python 3 and git, both already on any
machine that deploys websites.

It costs about 264 tokens in every session, which is the skill and the agent
announcing that they exist. The hook runs in the harness and adds nothing to
the model's context at all. Numbers from `claude plugin details varo`, not
estimated by hand.

## Using it

Open Claude Code in a folder holding a site. The hook speaks first:

```
## Static site in this folder (acme-brochure)

- Host: Cloudflare / Netlify / Vercel
- Config for more than one host in the same repo: wrangler.toml,
  netlify.toml, vercel.json. Only the host you actually deploy to reads
  its own file. Redirects and security headers written in the others do
  nothing.
- On branch `qa/pass-two`, 4 commit(s) ahead of `main`. The site deploys
  from `main`, so none of that work is live.
```

Two findings before anybody has typed a word, of the kind that stay true for
weeks because nothing inside the editor ever shows them.

From there:

- "publish it" runs the deploy and then checks that the deploy landed
- "audit the site" hands it to the auditor agent
- "why is my change not showing" usually has its answer in the hook output

## The rule the whole thing runs on

**Fetch it. Do not infer it.**

A file in a functions folder does not mean the endpoint is deployed. A header
in a config file does not mean the host sends it. A build script exiting 0 does
not mean it did anything. Each of those has shipped broken while the repository
looked correct, which is why a finding counts here when the live site answered,
and counts for nothing when it came from reading code and reasoning about what
the code probably does.

## What it does not do

No servers, no databases, no build system of its own. It works on files a host
serves, plus the small functions a host runs alongside them. When something
needs a real backend, it says so instead of stretching.

It also does not deploy on its own initiative. Publishing stays a step somebody
asks for.

## Checks

```bash
python3 tools/prova.py
```

Twenty-nine of them, a few seconds, run against throwaway repositories built on
the spot. They cover the plugin manifest, the hook's behaviour on a site, on a
folder that is not a site, outside git, and on a path that does not exist, and
they run the prose through `tools/stylecheck.py`, which enforces the writing
rules mechanically instead of by rereading.

## Licence

GPL-3.0.
