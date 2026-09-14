"""Explicit user vocabulary corrections. No model calls or automatic learning."""
import re

def apply_vocabulary(text, entries):
    rules = []
    for line in entries.splitlines()[:100]:
        if '=>' not in line:
            continue
        spoken, written = (part.strip() for part in line.split('=>', 1))
        if spoken and written and len(spoken) <= 100 and len(written) <= 200:
            rules.append((spoken, written))
    if not rules:
        return text
    mapping = {spoken.casefold(): written for spoken, written in rules}
    pattern = r'(?<!\w)(?:' + '|'.join(re.escape(s) for s in sorted(mapping, key=len, reverse=True)) + r')(?!\w)'
    return re.sub(pattern, lambda match: mapping[match.group(0).casefold()], text, flags=re.I)
