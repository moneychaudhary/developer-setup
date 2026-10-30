"""Read VS Code JSON with comments and trailing commas without executing code."""
import json
import re


def loads(text):
    output = []
    position = 0
    quoted = False
    escaped = False
    while position < len(text):
        char = text[position]
        if quoted:
            output.append(char)
            if escaped:
                escaped = False
            elif char == '\\':
                escaped = True
            elif char == '"':
                quoted = False
            position += 1
        elif char == '"':
            quoted = True
            output.append(char)
            position += 1
        elif text[position:position+2] == '//':
            end = text.find('\n', position)
            position = len(text) if end < 0 else end
        elif text[position:position+2] == '/*':
            end = text.find('*/', position+2)
            if end < 0:
                raise ValueError('Unterminated JSON comment')
            output.append(' ')
            position = end+2
        else:
            output.append(char)
            position += 1
    text = ''.join(output)
    output = []
    quoted = False
    escaped = False
    for position, char in enumerate(text):
        if not quoted and char == ',' and re.match(r'\s*[}\]]', text[position+1:]):
            continue
        output.append(char)
        if escaped:
            escaped = False
        elif quoted and char == '\\':
            escaped = True
        elif char == '"':
            quoted = not quoted
    return json.loads(''.join(output))
