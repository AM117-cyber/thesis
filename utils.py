import re
from enum import Enum, auto

import spacy

class LineType(Enum):
    SECTION = auto()
    IMAGE = auto()
    FIGURE = auto()
    TABLE = auto()
    LIST_IGNORE = auto()
    MATH = auto()
    CHAPTER = auto()
    PARAGRAPH = auto()
    COMMAND = auto()
    IGNORE = auto()
    COMMENT = auto()

class NoteType(Enum):
    MISSING_INTRO = "Una cosa no puede empezar con una subcosa"
    CHAPTER_MISSING_INTRO = "El capítulo debe tener un párrafo introductorio antes de una sección."
    ADJ = auto()

nlp = spacy.load("es_core_news_sm")

def merge_dicts_by_start_order(dict1, dict2):
    """
    Merge two dictionaries with [start, end] keys and concatenate their text values
    in order of increasing 'start' position.
    
    Args:
        dict1: First dictionary { (start, end): text }
        dict2: Second dictionary { (start, end): text }
    
    Returns:
        Merged text string (joined in start order)
    """
    # Combine both dictionaries into a single list of (start, end, text)
    combined = [
        (start, end, text)
        for (start, end), text in {**dict1, **dict2}.items()
    ]
    
    # Sort by 'start' position
    combined_sorted = sorted(combined, key=lambda x: x[0])
    
    # Extract texts in order and join with ""
    merged_text = "".join(text for (start, end, text) in combined_sorted)
    
    return merged_text

def detect_passive_voice(text):
    doc = nlp(text)
    spans = []

    for i in range(len(doc) - 1):
        token = doc[i]
        # Match any form of 'ser' as a VERB (e.g., "es", "fue", "son", "serán")
        if token.lemma_ == "ser" and token.pos_ in ("AUX", "VERB"):
            # Look ahead a few tokens for a past participle
            for j in range(i + 1, min(i + 2, len(doc))):
                next_token = doc[j]
                if (next_token.pos_ in ("VERB") and "VerbForm=Part" in next_token.morph) or (next_token.pos_ != "ADJ" and next_token.text.lower().endswith(("ado", "ido", "to", "so", "cho"))):  # Past participle
                    span = doc[i:j + 1]
                    spans.append((span.start_char, span.end_char))
                    break
    return spans

def detectar_primera_segunda_persona_y_adjetivos(texto):
    doc = nlp(texto)
    spans = []
    pronouns = {"yo", "tú", "vos", "usted", "ustedes", "nosotros", "nosotras", "vosotros", "vosotras", "me"}
    adj_spans = []
    for i, token in enumerate(doc):
        # Always highlight personal pronouns
        if token.text.lower() in pronouns and token.pos_ == "PRON":
            spans.append((token.idx, token.idx + len(token.text)))
        
        # Check for compound verbs (aux + participle) in 1st/2nd person
        if token.pos_ == "AUX" and ("Person=1" in token.morph or "Person=2" in token.morph):
            # Look ahead for participle
            for j in range(i + 1, min(i + 3, len(doc))):
                next_token = doc[j]
                if (next_token.pos_ == "VERB" and "VerbForm=Part" in next_token.morph):
                    span_start = token.idx
                    span_end = next_token.idx + len(next_token.text)
                    spans.append((span_start, span_end))
                    break
            spans.append((token.idx, token.idx + len(token.text)))
        
        # Check for simple verbs in 1st/2nd person
        elif token.pos_ == "VERB" and ("Person=1" in token.morph or "Person=2" in token.morph):
            spans.append((token.idx, token.idx + len(token.text)))
        
        # Check for adjectives
        elif token.pos_ == "ADJ":
            adj_spans.append((token.idx, token.idx + len(token.text)))
    
    return spans, adj_spans

def mark_passive_voice(doc_content:str) -> str:
    # Step 1: Highlight passive voice (ser + participle) and returns the text highlighted
    spans = detect_passive_voice(doc_content)
    offset = 0
    for start, end in spans:
        real_start = start + offset
        real_end = end + offset
        original = doc_content[real_start:real_end]
        wrapped = '\comment {'+original+'}{Voz p} '
        doc_content = doc_content[:real_start] + wrapped + doc_content[real_end:]
        offset += len(wrapped) - (end - start)
    return doc_content

def mark_first_second_person_and_adject(doc_content:str) ->str:
    # Step 2:[] Highlight first/second person verbs, pronouns, and adjectives
    persona_spans, adj_spans = detectar_primera_segunda_persona_y_adjetivos(doc_content)
    # Sort spans by start position to process them in order
    persona_spans.sort()
    offset = 0
    for start, end in persona_spans:
        real_start = start + offset
        real_end = end + offset
        # Skip if this span is already inside a previous highlight
        if any(s <= real_start and real_end <= e for (s, e) in persona_spans if s < start):
            continue
        original = doc_content[real_start:real_end]
        wrapped = '\comment {'+original+'}{Escribir en 3ra persona.} '
        doc_content = doc_content[:real_start] + wrapped + doc_content[real_end:]
        offset += len(wrapped) - (end - start)
    for start, end in adj_spans:
        real_start = start + offset
        real_end = end + offset
        # Skip if this span is already inside a previous highlight
        if any(s <= real_start and real_end <= e for (s, e) in adj_spans if s < start):
            continue
        original = doc_content[real_start:real_end]
        wrapped = '\comment {'+original+'}{Adjetivo.} '
        doc_content = doc_content[:real_start] + wrapped + doc_content[real_end:]
        offset += len(wrapped) - (end - start)
    return doc_content

def mark_weasel_spanglish(weasel_words, spanglish_words, doc_content:str) -> str:
    
    for word in weasel_words:
        pattern = r'\b' + re.escape(word) + r'\b'
        doc_content = re.sub(
            pattern,
            lambda m: '\comment {'+ m.group(0) + '}{Palabra de comadreja} ',
            doc_content,
            flags=re.IGNORECASE
        )
    for word in spanglish_words:
        pattern = r'\b' + re.escape(word) + r'\b'
        doc_content = re.sub(
            pattern,
            lambda m: '\comment {'+ m.group(0) + '}{Spanglish}',
            doc_content,
            flags=re.IGNORECASE
        )
    return doc_content


def line_classifier(line: str) -> LineType:
    """Classifies a LaTeX line into different types, handling leading commands."""
    line = line.strip()
    
    # Handle cases like "\centering \begin{figure}"
    if '\\begin{' in line:
        # Extract just the \begin{...} part if there are preceding commands
        begin_match = re.search(r'\\begin\{([^}]*)\}', line)
        if begin_match:
            # Reconstruct just the begin statement for classification
            begin_part = f"\\begin{{{begin_match.group(1)}}}"
            line = begin_part
    if re.match(r'^\s*%', line):
        return LineType.COMMENT
    # Check for chapter commands (highest priority)
    if re.match(r'^\s*\\(chapter|part)\*?\{', line):
        return LineType.CHAPTER

    # Check for section/subsection with optional *
    if re.match(r'^\s*\\(sub)*section\*?\{', line):
        return LineType.SECTION

    # Check for various commands
    if re.match(r'^\s*\\(maketitle|tableofcontents|listoffigures|listoftables|usepackage|documentclass|setlength|addbibresource|hypersetup)', line, re.IGNORECASE):
        return LineType.COMMAND

    # Check for image inclusion
    if re.match(r'^\s*\\includegraphics(\[.*\])?\{', line):
        return LineType.IMAGE

    # Check for figure environment
    if re.match(r'^\\begin\{figure', line, re.IGNORECASE):
        return LineType.FIGURE
    
    # Check for table environment
    if re.match(r'^\\begin\{tabular|\begin\{table', line, re.IGNORECASE):
        return LineType.TABLE
    
    # Check for list environments to ignore   otherlanguage!!!!
    if re.match(r'^\\begin\{enumerate|\begin\{description', line, re.IGNORECASE):
        return LineType.LIST_IGNORE
    
    # Check for math environments
    if re.match(r'^\\begin\{equation|\begin\{align|\begin\{gather|\begin\{multiline', line, re.IGNORECASE):
        return LineType.MATH
    
    # Check for other non-text environments (excluding document, abstract, etc.)
    if re.match(r'^\\begin\{(?!document|abstract|frame|quote|multicols|parcolumns|itemize)', line, re.IGNORECASE):
        return LineType.IGNORE
    
    # Default to paragraph
    return LineType.PARAGRAPH

def check_number(line: str) -> str:
    """
    Highlights the number portion in section/chapter commands.
    Example:
    Input:  \section{1.1.3 Location}
    Output: \section{\sethlcolor{orange}\hl{1.1.3} Location}
    """
    # Match section/chapter commands with content
    match = re.match(r'^\s*(\\(?:chapter|(?:sub)*section)\*?)\s*\{([^}]*)\}', line)

    
    command, content = match.groups()
    
    # Find the number portion (digits and dots) at start of content
    number_match = re.match(r'^(\s*\d+(?:\.\d+)*)', content)
    if not number_match:
        return line  # No number found
    
    number = number_match.group(1)
    remaining_content = content[len(number):]
    
    # Reconstruct with highlighted number
    color = "\sethlcolor{orange}"
    highlighted = f"{command}{{{color}\hl{{{number.strip()}}}{remaining_content}}}\n"
    highlighted += "\\notaparaelautor{No pongas el número de la sección tú a mano. Deja que LaTeX se encargue de eso.}\n"
    return highlighted

def add_note(type: NoteType,line: str) -> str:
    line += "\n" + "\\notaparaelautor{" + type.value + "}\n"
    return line

def check_spanglish(line: str) -> str:
    spanglish_words = ["parsear, revolver"]

# def get_begin_end_block(lines, index): # if the block is not to be ignored I gather each paragraph and process it with th corresponding method
#     line = lines[index]
#     # Handle cases like "\centering \begin{figure}"
#     # Extract just the \begin{...} part if there are preceding commands
#     begin_match = re.search(r'\\begin\{([^}]*)\}', line)
#     if begin_match:
#         # Reconstruct just the begin statement for classification
#         environment = begin_match.group(1)
#     if environment:
#         begin_end_block = [line]  # Start with the \begin line
#         index += 1
#         depth = 1  # Track nested environments
        
#         while index < len(lines) and depth > 0:
#             current_line = lines[index]
#             begin_end_block.append(current_line)    
            
#             # Check for nested environments
#             if '\\begin\{' in line:
#                 depth += 
#             if re.match(r'^\\begin\{', current_line):
#                 depth += 1
#             elif re.match(r'^\\end\{' + re.escape(environment) + r'\}', current_line):
#                 depth -= 1
            
#             index += 1
#         begin_end_block = '\n'.join(begin_end_block)  # Preserve original line breaks
#         return begin_end_block, index-1
#     return line, index-1


def get_begin_end_block(lines, index):
    """Processes nested LaTeX environments across multiple lines."""
    line = lines[index]
    
    # Initialize tracking
    depth = 0
    
    begin_end_block = []
    while index < len(lines):
        # Find all begins/ends in current line
        begins = list(re.finditer(r'\\begin\{([^}]*)\}', line))
        ends = list(re.finditer(r'\\end\{([^}]*)\}', line))
        
        # Process matches in order of appearance
        matches = sorted(begins + ends, key=lambda m: m.start())

        for match in matches:
            if match in begins:  # It's a begin
                depth += 1
            else:  # It's an end
                depth -= 1
        begin_end_block.append(line) 
        
        if depth > 0:
            index +=1
            if index <len(lines)-1:
                line = lines[index]

        else:
            break
    begin_end_block = '\n'.join(begin_end_block)  # Preserve original line breaks
    return begin_end_block, index

















def process_section_chapter_declaration(lines, i, weasels, spanglish):
    line = lines[i]
    line = check_number(line) # if the number is written it highlights it
    # line = mark_first_second_person_and_adject(line)
    # line = mark_passive_voice(line)
    line = mark_weasel_spanglish(weasels, spanglish, line)
    if i < len(lines)-1 and line_classifier(lines[i+1]) is LineType.SECTION:
        # print(f"No intro after {line_type.name}: {line}")
        line = add_note(NoteType.MISSING_INTRO, line)
        # line = check_spanglish(line)
    
    return line

def separate_latex_commands(text):

    '''Receives a paragraph that might contain latex commands or mathematic elements, which it separates into a dict with spans to ignore and dict with span to analyze'''


    # Sub-pattern to extract parts from a LaTeX command
    command_decomposer = re.compile(
        r"""
        \\(?P<name>[a-zA-Z]+)\*?                # Command name
        \s*
        (?:\[(?P<options>[^\]]*)\])?            # Optional options
        \s*
        (?:\((?P<label>[^\)]*)\))?              # Optional label
        \s*
        (?:\{(?P<content>[^{}]*)\})?             # Optional {content}
        """,
        re.VERBOSE
    )



    allowed_content_spans = []
    ignored_spans = []
    words_with_positions = []

    # Step 1: Process allowed LaTeX commands (e.g., \textbf{}, \hl{})
    # latex_pattern = re.compile(r'\\([a-zA-Z]+)\*?(?:\[[^\]]*\])?{([^}]*)}')
    latex_pattern = re.compile(
        r"""
        (?P<command>
            \\[a-zA-Z]+\*?                      # Command name
            \s*                                 # Optional space
            (?:\[[^\]]*\])?                     # Optional [options]
            \s*
            (?:\([^\)]*\))?                     # Optional (label)
            \s*
            \{[^{}]*\}
            |
            \\[a-zA-Z]+\*?                      # Command name
            \s*                                 # Optional space
            (?:\[[^\]]*\])?                     # Optional [options]
            \s*
            (?:\([^\)]*\))?                     # Optional (label)
        )
        |
        (?P<math>
            \$\$.*?\$\$                         # Display math with $$
            |
            \$[^$]+\$                           # Inline math with $
            |
            \\\[.*?\\\]                         # Display math with \[...\]
            |
            \\\(.*?\\\)                         # Inline math with \( ... \)
        )
        """,
        re.VERBOSE | re.DOTALL
    )

    allowed_commands = {'textbf', 'hl', 'colchunk','comment'}
    current_pos = 0
    cleaned_parts = []

    parts_to_ignore = {}
    parts_to_analyze = {}

    for match in latex_pattern.finditer(text):
        start, end = match.span()

        if match.group("command"):
            
            cmd_text = match.group("command")
            
            submatch = command_decomposer.match(cmd_text)

            if submatch:
                command = submatch.group("name")
                argument = submatch.group("content")
            else:
                print("Unparsed command:", cmd_text)
                command = "unrecognized"
        else: # it's math, so we can get the length of it directly
            command = "math"
        if command in allowed_commands:
            # Calculate content positions in original text
            prefix_len = len(match.group(0)) - len(argument) - 1
            content_start = start + prefix_len
            content_end = end - 1

            # Mark command syntax as ignored
            ignored_spans.extend([(start, content_start), (content_end, end)])
            allowed_content_spans.append((content_start, content_end))

            # Process content words
            doc = nlp(argument)
            for token in doc:
                if token.is_alpha and len(token.text) > 2:
                    word_start = content_start + token.idx
                    word_end = word_start + len(token.text)
                    words_with_positions.append((word_start, word_end, token.text.lower()))

            # Build cleaned text for sentence segmentation
            cleaned_parts.extend([
                text[current_pos:start],
                ' ' * (content_start - start),  # Replace command prefix
                argument,
                ' ' * (end - content_end - 1)   # Replace command suffix
            ])
            current_pos = end
        else:
            # Ignore other commands entirely
            ignored_spans.append((start, end))
            cleaned_parts.append(text[current_pos:start] + ' ' * (end - start))
            current_pos = end



    # Step: Extend ignored_spans with trailing {...} blocks if they appear after an unallowed command

    # This is necessary because with the regex I can't find a {} inside another one, so \h1{\textbf{jj}} would cause problems for example
    i = 0
    while i < len(ignored_spans):
        span_start, span_end = ignored_spans[i]

        # Skip whitespace to look for the next non-space character
        j = span_end
        while j < len(text) and text[j].isspace():
            j += 1

        # Check if next char is opening brace
        if j < len(text) and text[j] == '{':
            brace_start = j
            depth = 1
            j += 1
            while j < len(text) and depth > 0:
                if text[j] == '{':
                    depth += 1
                elif text[j] == '}':
                    depth -= 1
                j += 1

            if depth == 0:
                brace_end = j
                ignored_spans.append((brace_start, brace_end))

        i += 1
    all_ignored = sorted(ignored_spans)
    
    index = 0
    ignored_index = 0
    while index < len(text):
        if ignored_index < len(all_ignored):
            curr_start, curr_end = all_ignored[ignored_index]
        else:
            # write what is remaining of the text and break
            parts_to_analyze[index, len(text)] = text[index:len(text)]
            break
        if index < curr_start:
            parts_to_analyze[index, curr_start] = text[index:curr_start]

        parts_to_ignore[curr_start, curr_end] = text[curr_start:curr_end]
        ignored_index+=1
        index = curr_end
    return parts_to_ignore, parts_to_analyze