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
    BEGIN_BLOCK_START_END = auto()
    COMMAND = auto()
    IGNORE = auto()
    COMMENT = auto()

class CommandType(Enum):

    MATH = auto()
    CLOSE_BRACE = auto()
    COMMAND = auto()

class NoteType(Enum):
    MISSING_INTRO = "Una cosa no debe empezar con una subcosa"
    ITEM_PUNCTUATION = "Cada item debe terminar con un signo de puntuación o con: \textless, y\textgreater, \textless, o\textgreater "
    CHAPTER_MISSING_INTRO = "El capítulo debe tener un párrafo introductorio antes de una sección."
    ADJ = auto()

nlp = spacy.load("es_core_news_sm")

def fix_cite_usage(latex_text):
    """
    Finds and comments problematic \cite commands where:
    1. Preceded by punctuation (.,;:!?) with optional whitespace
    2. Immediately preceded by any non-whitespace character except ~
    
    Wraps as: [preceding text] \comment{\cite{content}}{Incorrect citation format}
    """
    # Pattern to match wrong citations
    pattern = r'''
    (
        ([^\s~] |       # Option 1: Non-whitespace char that's not ~
            [.,;:!?]\s*    # Option 2: Punctuation followed by optional whitespace
        )
        (\\cite\{.*?\})    # The \cite command itself
    )
    '''
    
    # Replacement function
    def replacer(match):
        preceding_char = match.group(2).strip()
        cite_cmd = match.group(3)
        # Insert space between preceding text and comment
        return f'{preceding_char} \\comment{{{cite_cmd}}}{{Incorrect citation format}}'
    
    # Apply replacement
    fixed_text = re.sub(
        pattern,
        replacer,
        latex_text,
        flags=re.VERBOSE
    )
    
    return fixed_text

def get_package_details(line):
    """Extract package name and options from a \\usepackage command."""
    
    match = re.match(r"\\usepackage(?:\[(.*?)\])?\{(.*?)\}", line.strip())
    if match:
        # options = match.group(1) or ""
        pkg_name = match.group(2)
        return pkg_name
    return line

def sanitize_preamble(original_preamble, my_commands):
    lines = original_preamble.split('\n')
    commented_preamble = []

    # Extract packages we're adding (to check for duplicates)
    my_packages = []
    for cmd in my_commands:
        pkg_name= get_package_details(cmd)
        if pkg_name:
            my_packages.append(pkg_name)
    conflict = False

    for line in lines:
        line_stripped = line.strip()
        pkg_name = get_package_details(line_stripped)
        
        
        # Case 1: Duplicate package (e.g., xcolor in original vs. xcolor[dvipsnames] in mine)
        if pkg_name in my_packages:
            conflict = True
            line = f"% [AUTO-REMOVED DUPLICATE] {line}"
        
        
        # Case 2: Known conflicts (e.g., soul vs. hyperref)
        # if not conflict_found:
        #     for pkg, conflict_list in conflicts.items():
        #         for conflict_cmd in conflict_list:
        #             if re.search(re.escape(conflict_cmd), line_stripped):
        #                 line = f"% [AUTO-REMOVED CONFLICT] {line}"
        #                 conflict_found = True
        #                 break
        #         if conflict_found:
        #             break
        
        commented_preamble.append(line)
    
    # Insert new commands after sanitized preamble
    new_preamble = "\n".join(commented_preamble) + "\n" + "\n".join(my_commands) + "\n"
    
    return new_preamble, conflict

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

def detectar_primera_segunda_persona(texto):
    doc = nlp(texto)
    spans = {}
    pronouns = {"yo", "tú", "vos", "usted", "ustedes", "nosotros", "nosotras", "vosotros", "vosotras", "me"}
    adj_spans = []
    i = 0
    while i < len(doc):
        token = doc[i]
        if not token.text.isalpha():
            i+=1
            continue
        # Always highlight personal pronouns
        if token.text.lower() in pronouns and token.pos_ == "PRON":
            spans[token.idx, token.idx + len(token.text)] = "Person"
        
        # Check for compound verbs (aux + participle) in 1st/2nd person
        if token.pos_ == "AUX" and ("Person=1" in token.morph or "Person=2" in token.morph):
            # Look ahead for participle
            compound = False
            for j in range(i + 1, min(i + 3, len(doc))):
                next_token = doc[j]
                if (next_token.pos_ == "VERB" and "VerbForm=Part" in next_token.morph):
                    span_start = token.idx
                    span_end = next_token.idx + len(next_token.text)
                    spans[span_start, span_end] = "Person"
                    i = span_end
                    compound = True
                    break
            if not compound:
                spans[token.idx, token.idx + len(token.text)] = "Person"
            
        
        # Check for simple verbs in 1st/2nd person
        elif token.pos_ == "VERB" and ("Person=1" in token.morph or "Person=2" in token.morph):
            print(token.morph)
            spans[token.idx, token.idx + len(token.text)] = "Person"
        
        # Check for adjectives
        ##############################################
        ############# COMMENTING ADJs FOR NOW ########
        ##############################################
        # elif token.pos_ == "ADJ":
        #     spans[token.idx, token.idx + len(token.text)] = "ADJ"
        i+=1
    return spans


def mark_first_second_person(doc_content:str, comments) ->str:
    # Step 2:[] Highlight first/second person verbs, pronouns, and adjectives
    spans = detectar_primera_segunda_persona(doc_content)
    # Sort spans by start position to process them in order
    spans = sorted(spans.items(), key=lambda x: x[0][0])
    offset = 0
    index = 0
    while index < len(spans):
        curr_span = spans[index]
        start = curr_span[0][0]
        end = curr_span[0][1]
        real_start = start + offset
        real_end = end + offset
        # Skip if this span is already inside a previous highlight
        # if any(s <= real_start and real_end <= e for (s, e) in spans.keys() if s < start):
        #     continue
        original = doc_content[real_start:real_end]
        comment_text = "{Escribir en 3ra persona} "
        if curr_span[1] == "ADJ":
            comment_text = "{Adjetivo} "
        wrapped = '\comment {'+original+'}' + comment_text
        comments +=1
        doc_content = doc_content[:real_start] + wrapped + doc_content[real_end:]
        offset += len(wrapped) - (end - start)
        index += 1

    return doc_content, comments

def mark_passive_voice(doc_content:str, comments) -> str:
    # Step 1: Highlight passive voice (ser + participle) and returns the text highlighted
    spans = detect_passive_voice(doc_content)
    offset = 0
    for start, end in spans:
        real_start = start + offset
        real_end = end + offset
        original = doc_content[real_start:real_end]
        wrapped = '\comment {'+original+'}{Voz pasiva} '
        comments +=1
        doc_content = doc_content[:real_start] + wrapped + doc_content[real_end:]
        offset += len(wrapped) - (end - start)
    return doc_content, comments


def mark_weasel_spanglish(weasel_words, spanglish_words, doc_content:str, comments) -> str:
    
    for word in weasel_words:
        pattern = r'\b' + re.escape(word) + r'\b'
        new_content, num_subs = re.subn(
            pattern,
            lambda m: r'\comadreja{' + m.group(0) + '}',
            doc_content,
            flags=re.IGNORECASE
        )
        if num_subs > 0:
            doc_content = new_content
            comments += num_subs

    for word in spanglish_words:
        pattern = r'\b' + re.escape(word) + r'\b'
        new_content, num_subs = re.subn(
            pattern,
            lambda m: r'\comment {' + m.group(0) + '}{Anglicismo}',
            doc_content,
            flags=re.IGNORECASE
        )
        if num_subs > 0:
            doc_content = new_content
            comments += num_subs
    return doc_content, comments


def line_classifier(line: str) -> LineType:
    """Classifies a LaTeX line into different types, handling leading commands."""
    line = line.strip()
    print(line)
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
    if re.match(r'^\s*\\(maketitle|tableofcontents|listoffigures|listoftables|usepackage|documentclass|setlength|addbibresource|hypersetup|large|setcounter|newpage)', line, re.IGNORECASE):
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
    # if re.match(r'^\\begin\{enumerate|\begin\{description', line, re.IGNORECASE):
        # return LineType.LIST_IGNORE
    
    # Check for math environments
    if re.match(r'^\\begin\{equation|\begin\{align|\begin\{gather|\begin\{multiline', line, re.IGNORECASE):
        return LineType.MATH

    if line == "\[":
        return LineType.MATH

    if re.match(r'^\\begin\{(document|abstract|frame|quote|multicols|parcolumns|itemize|enumerate|description)', line, re.IGNORECASE):
        return LineType.BEGIN_BLOCK_START_END
    # Check for other non-text environments (excluding document, abstract, etc.)
    if re.match(r'^\\begin\{', line, re.IGNORECASE):
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
    
    highlighted = f"{command}{{\\textcolor{{orange}}{{{number.strip()}}}{remaining_content}}}\n"
    highlighted += "\\notaparaelautor{No pongas el número de la sección tú a mano. Deja que LaTeX se encargue de eso.}\n"
    return highlighted

def add_note(type: NoteType,line: str) -> str:
    line += "\n" + "\\notaparaelautor{" + type.value + "}\n"
    return line

def check_spanglish(line: str) -> str:
    spanglish_words = ["parsear, revolver"]

def jump_inline_comments(text: str) -> str:
    """
    Moves inline LaTeX comments to a new line.

    A comment is the '%' symbol and everything that follows it on a line.
    This function only moves a comment if it is "inline," meaning it is
    preceded by non-whitespace characters on the same line. A line jump is
    inserted right before the comment.

    - 'Text % comment' becomes 'Text\n% comment'.
    - '% Full line comment' is NOT changed.
    - '  % Indented comment' is NOT changed.
    - 'A sentence with 50\% profit.' is NOT changed (handles escaped percent).

    Args:
        text: The input string containing LaTeX code.

    Returns:
        A new string with inline comments moved to their own lines.
    """
    processed_lines = []
    
    for line in text.splitlines():
        # This regex finds the first '%' that is NOT preceded by a '\'.
        # (?<!\\) is a "negative lookbehind". It asserts that the character
        # immediately preceding the current position is not a backslash.
        match = re.search(r'(?<!\\)%', line)

        if match:
            # A potential comment symbol was found.
            comment_start_index = match.start()
            content_before_comment = line[:comment_start_index]
            comment_part = line[comment_start_index:]

            # The core condition: is there any non-whitespace text before the '%'?
            if content_before_comment.strip():
                # Yes. This is an inline comment.
                # Append the content before the comment (stripping trailing space).
                processed_lines.append(content_before_comment.rstrip())
                # Append the comment part as a new "line".
                processed_lines.append(comment_part)
            else:
                # No. The line starts with whitespace and then a '%'.
                # This is a full-line comment, so we keep the original line.
                processed_lines.append(line)
        else:
            # No comment symbol found on this line, so keep it as is.
            processed_lines.append(line)
            
    # Join the processed lines back together, which inserts the newline
    # between the content and the moved comment.
    return '\n'.join(processed_lines)


def format_latex_commands(text: str) -> str:
    """
    Finds specific LaTeX commands and adds line breaks around them,
    but only on lines that are not LaTeX comments.

    A LaTeX comment is any line that starts with a '%' character,
    potentially preceded by whitespace.

    The function finds the following commands:
    - \\begin{...}, \\end{...}
    - \\chapter{...}, \\section{...}, \\subsection{...}, \\subsubsection{...}, etc.
    - \\[, \\]
    - \\item

    If a command is found on a non-commented line and it is preceded by a
    non-whitespace character on that same line, a line break is added before it.
    A line break is also added after the command's body, except for the \\item
    command.

    Examples:
    - 'abcd \\section{...}' becomes 'abcd\\n\\section{...}\\n'
    - '    \\section{...}' (at start of a line) remains unchanged.
    - '% my notes \\section{...}' remains unchanged.

    Args:
        text: The input string containing LaTeX code.

    Returns:
        A new string with formatted line breaks.
    """
    # --- The original regex logic, which is perfect for processing a single line ---

    # This part of the pattern defines all the commands we want to find.
    # It is wrapped in parentheses to become a capturing group (group 2).
    command_pattern_group = (
        r'('
        r'\\(?:begin|end)\{[a-zA-Z0-9*]+\}'             # \begin{...} or \end{...}
        # Updated to handle starred versions like \section*{...}
        r'|\\(?:chapter|(?:sub)*section)\*?\{.*?\}'
        r'|\\item'                                      # \item
        r'|\\\[|\\\]'                                   # \[ or \]
        r')'
    )

    # The full pattern now does two things:
    # 1. `(\S.*?)`: This is group 1. It captures any preceding text on the same line.
    # 2. `command_pattern_group`: This is group 2, which captures the command itself.
    pattern = re.compile(r'(\S.*?)' + command_pattern_group)

    def replacer(match):
        """
        This function is called for each match and defines the replacement.
        """
        preceding_text = match.group(1)
        command = match.group(2)
        result = preceding_text + '\n' + command
        if not command.startswith(r'\item'):
            result += '\n'
        return result

    # --- New logic to process the text line by line ---

    lines = text.splitlines()
    processed_lines = []

    for line in lines:
        # Check if the line is a comment. A comment starts with '%',
        # ignoring any leading whitespace.
        if line.strip().startswith('%'):
            # If it's a comment, add it to our results without changes.
            processed_lines.append(line)
        else:
            # If it's not a comment, apply the regex substitution to the line.
            processed_line = pattern.sub(replacer, line)
            processed_lines.append(processed_line)

    # Join the processed lines back into a single string.
    # splitlines() removes newlines, so we must add them back.
    return '\n'.join(processed_lines)

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


def get_math_block(lines, index):
    """Processes LaTeX math environments across multiple lines."""
    line = lines[index]
    
    depth = 0
    math_block = []
    
    while index < len(lines):
        # Find all math begin/end markers
        begins = list(re.finditer(r'\[', line))
        ends = list(re.finditer(r'\]', line))
        
        # Process matches in order
        matches = sorted(begins + ends, key=lambda m: m.start())

        for match in matches:
            if match in begins:
                depth += 1
            else:
                depth -= 1
        
        math_block.append(line) 
        
        if depth > 0:
            index += 1
            if index < len(lines):
                line = lines[index]
        else:
            break
    
    math_block = '\n'.join(math_block)  # Preserve line breaks
    return math_block, index

















def process_section_chapter_declaration(lines, i, weasels, spanglish):
    line = lines[i]
    line_additions = ""
    line = check_number(line) # if the number is written it highlights it
    # line = mark_first_second_person_and_adject(line)
    # line = mark_passive_voice(line)
    errors = ''
    doc = nlp(line)
    for word in doc:
        if word.text in weasels:
            errors += f"la palabra comadreja: {word.text}, "
        if word.text in spanglish:
            errors += f"el anglicismo: {word.text}, "
    if len(errors) > 0:
        line_additions += "\n" + r"\notaparaelautor{En el nombre del capítulo o sección pusiste: " + errors.strip(", ") + "} \n"
    next_line = ''
    while i < len(lines)-1 and next_line.strip() == "":
        next_line = lines[i+1]
        i+=1
    
    next_line_type = line_classifier(next_line) 
    if next_line_type is LineType.SECTION or next_line_type is LineType.BEGIN_BLOCK_START_END or next_line.strip().startswith(r"\paragraph{"):
        # print(f"No intro after {line_type.name}: {line}")
        line_additions = add_note(NoteType.MISSING_INTRO, line_additions)
        # line = check_spanglish(line)
    
    return line, line_additions














#     # Helper to add span to the correct list
# def add_span(span, is_process):
#         if span[0] >= span[1]:
#             return
#         (process_spans if is_process else ignore_spans).append(span)

def find_balance_symbol(start_symbol, end_symbol, text, position):
    depth = 1
    while position < len(text) and depth > 0:
        character = text[position]
        if character is start_symbol:
            depth +=1
        if character is end_symbol:
            depth -= 1
        position +=1
    return position

def get_first_non_empty_char(text, position):
    character = text[position]
    init_position = position
    while character == " " and position < len(text):
        position+=1
        character = text[position]
    return position, character

def call_optional_method(text, position, envs, to_ignore, to_analyze):
    '''It receives a list of envs ([], (), {}, etc) that could follow a command in a certain order optionally and 
        if it finds them it adds them to ignore, while adding to analyze the spaces between them.
        This method is only for commands to ignore'''
    env_index = 0
    while env_index < len(envs) and position < len(text):
        character = text[position]
        init_position = position
        while character == " ":
            position+=1
            character = text[position]
        if position != init_position:
            to_analyze[init_position, position] = text[init_position: position]
        while env_index < len(envs):
            if character == envs[env_index][0]:
                end = find_balance_symbol(envs[env_index][0], envs[env_index][1], text, position+1)
                to_ignore[position, end] = text[position: end]
                position = end
                env_index += 1
                break
            env_index += 1
    return position


def commands_to_consider_method(command, text, position, matches, index, to_ignore, to_analyze):
    '''It receives a dictionay of envs {[], (), {}, etc} in which each env is assign True or False to identify if the content of them should be ignored.
        When it finds them (we assume all the envs appear) it adds them to ignore or analyze accordingly, while adding to analyze the spaces between them.
        This method is only for commands to analyze'''

    # by default I will consider the content of first {} to analyze

    #textbf', 'hl','comment', 'textcolor
    if command == "comment":
        # consider first {} and ignore second {}
        new_position, character = get_first_non_empty_char(text, position)
        if position != new_position:
            to_analyze[position,new_position] = text[position:new_position]
            position = new_position
        if character != '{':
            return position, index

        to_ignore[position,position] = '{'
        position +=1
        position = process_command_arg1(1, position, matches, index, text, to_ignore, to_analyze)
        # ignoring second {}
        position = call_optional_method(text, position, ['{}'], to_ignore, to_analyze)
        return position, index
    if command == "textcolor":
        # ignore first {} and consider second {}
        position = call_optional_method(text, position, ['{}'], to_ignore, to_analyze)
        new_position, character = get_first_non_empty_char(text, position)
        if position != new_position:
            to_analyze[position,new_position] = text[position:new_position]
            position = new_position
        if character != '{':
            return position, index

        to_ignore[position,position] = '{'
        position +=1
        position = process_command_arg1(1, position, matches, index, text,to_ignore, to_analyze)
        return position, index
    else:
        # default
        new_position, character = get_first_non_empty_char(text, position)
        if position != new_position:
            to_analyze[position,new_position] = text[position:new_position]
            position = new_position
        if character != '{':
            return position, index

        to_ignore[position,position] = '{'
        position +=1
        position = process_command_arg1(1, position, matches, index, text,to_ignore, to_analyze)
        return position, index






    # # Step 1: mark all math spans as ignored
    # for m in math_pattern.finditer(text):
    #     add_span(m.span(), False)

    # Step 2: mark all command spans
def separate_latex_commands(text):

    to_ignore = {}
    to_analyze = {}

    # Matches LaTeX commands like \command[opt](label){arg}{mod1}{mod2}
    command_pattern = re.compile(
        r'''\\[a-zA-Z@]+
        ''',
        re.VERBOSE
    )

    # Matches math environments
    math_pattern = re.compile(
        r'(?P<math>\$\$.*?\$\$|\$.*?\$|\\\[.*?\\\]|\\\(.*?\\\))',
        re.DOTALL
    )

    brace_end = re.compile(r'}')

    matches = {}
    for m in command_pattern.finditer(text):
        matches[m.span()] = [CommandType.COMMAND]
    for m in math_pattern.finditer(text):
        matches[m.span()] = [CommandType.MATH]
    for m in brace_end.finditer(text):
        matches[m.span()] = [CommandType.CLOSE_BRACE]
    matches = sorted(matches.items(), key=lambda x: x[0][0])
    process_command_arg1(0,0,matches, 0, text, to_ignore, to_analyze)
    # print(to_analyze)
    # print("\n\n")
    # print(to_ignore)
    return to_ignore, to_analyze


def process_command_arg1(depth, curr_pos, matches, index, text, to_ignore, to_analyze):
    commands_to_consider = ['textbf', 'textit', 'hl','comment', 'textcolor', 'comadreja']
    matches = list(matches) 
    # matches elements are in the form: [[start, end], type]
    index = index
    while index < len(matches):
        match = matches[index]
        # print(f'MATCH FOUND:{match[1]}')
        if match[0][0] < curr_pos:
            index +=1
            continue
        valid_text = text[curr_pos: match[0][0]]
        if valid_text != "":
            to_analyze[curr_pos, match[0][0]] = valid_text
        curr_pos = match[0][1]
        if match[1][0] is CommandType.MATH:
            to_ignore[match[0][0], match[0][1]] = text[match[0][0]: match[0][1]] # fix math
        if match[1][0] is CommandType.CLOSE_BRACE:
            if depth > 0:
                depth -= 1
                to_ignore[match[0][0], match[0][1]] = text[match[0][0]: match[0][1]]
                if depth <= 0:
                    return curr_pos
            else:
                to_analyze[match[0][0], match[0][1]] = text[match[0][0]: match[0][1]]
        print(match[1])
        if match[1][0] is CommandType.COMMAND:
            command_name = text[match[0][0]+1:match[0][1]] # +1 to skip \
            to_ignore[match[0][0], match[0][1]] = text[match[0][0]: match[0][1]]
            if command_name in commands_to_consider:
                curr_pos, index = commands_to_consider_method(command_name, text, curr_pos, matches, index, to_ignore, to_analyze)
            else:
                curr_pos = call_optional_method(text, match[0][1], ['[]','()','{}'], to_ignore, to_analyze)
                 
        index +=1
    if curr_pos < len(text):
        to_analyze[curr_pos, len(text)] = text[curr_pos: len(text)]
              

def insert_ambiguity_comment(text: str, line_idx: int, sentence_idx: int, reason: str) -> str:
    lines = text.splitlines()
    
    if line_idx >= len(lines):
        print(f"Missing line at index {line_idx}")
        return text

    line = lines[line_idx].strip()
    doc = nlp(line)
    sentences = [sent.text.strip() for sent in doc.sents]

    if sentence_idx >= len(sentences):
        print(f"Missing sentence at index {sentence_idx} in line {line_idx}")
        return text

    # Insert "comment" at the beginning of the target sentence
    sentences[sentence_idx] = r"\comment{Ambiguity}{" f"{reason}" + "} " + sentences[sentence_idx]

    # Reconstruct the line and text
    modified_line = ' '.join(sentences)
    lines[line_idx] = modified_line
    return '\n'.join(lines)

def add_section_note(text, section_name, suggestion)->str:
    lines = text.splitlines()
    pattern = re.compile(rf'^\s*\\(sub)*section\*?\{{\s*{re.escape(section_name)}\s*\}}')

    new_lines = []
    inserted = False

    i = 0
    while i < len(lines):
        new_lines.append(lines[i])
        if not inserted and pattern.match(lines[i]):
            # Insert note after the matched section declaration
            new_lines.append("\n\\notaparaelautor{"+ suggestion + "}\n")
            inserted = True
        i += 1

    return "\n".join(new_lines)


def add_chapter_note(text: str, suggestion) -> str:
    lines = text.splitlines()
    chapter_pattern = re.compile(r'^\s*\\chapter\*?\{.*\}')
    
    new_lines = []
    inserted = False

    for i, line in enumerate(lines):
        new_lines.append(line)
        if not inserted and chapter_pattern.match(line):
            new_lines.append("\n\\notaparaelautor{"+ suggestion + "}\n")
            inserted = True

    return "\n".join(new_lines)

















# def separate_latex_commands_with_errors(text):

#     '''Receives a paragraph that might contain latex commands or mathematic elements, which it separates into a dict with spans to ignore and dict with span to analyze'''


#     # Sub-pattern to extract parts from a LaTeX command
#     command_decomposer = re.compile(
#         r"""
#         \\(?P<name>[a-zA-Z]+)\*?                # Command name
#         \s*
#         (?:\[(?P<options>[^\]]*)\])?            # Optional options
#         \s*
#         (?:\((?P<label>[^\)]*)\))?              # Optional label
#         \s*
#         (?:\{(?P<content>[^{}]*)\})?             # Optional {content}
#         """,
#         re.VERBOSE
#     )



#     allowed_content_spans = []
#     ignored_spans = []
#     words_with_positions = []

#     # Step 1: Process allowed LaTeX commands (e.g., \textbf{}, \hl{})
#     # latex_pattern = re.compile(r'\\([a-zA-Z]+)\*?(?:\[[^\]]*\])?{([^}]*)}')
#     latex_pattern = re.compile(
#         r"""
#         (?P<command>
#             \\[a-zA-Z]+\*?                      # Command name
#             \s*                                 # Optional space
#             (?:\[[^\]]*\])?                     # Optional [options]
#             \s*
#             (?:\([^\)]*\))?                     # Optional (label)
#             \s*
#             (?:
#                 \{                              # Either has {
#                     [^{}]*                      #   content inside
#                 \}
#                 |                               # OR
#                 (?!\s*[a-zA-Z])                # Not followed by a letter
#                 (?=\s*[^a-zA-Z\s]|\s*$)        # Must be followed by non-letter or EOL
#             )
#         )
#         |
#         (?P<math>
#             \$\$.*?\$\$                         # Display math with $$
#             |
#             \$[^$]+\$                           # Inline math with $
#             |
#             \\\[.*?\\\]                         # Display math with \[...\]
#             |
#             \\\(.*?\\\)                         # Inline math with \( ... \)
#         )
#         """,
#         re.VERBOSE | re.DOTALL
#     )

#     allowed_commands = {'textbf', 'hl', 'colchunk','comment'}
#     current_pos = 0
#     cleaned_parts = []

#     parts_to_ignore = {}
#     parts_to_analyze = {}

#     for match in latex_pattern.finditer(text):
#         start, end = match.span()

#         if match.group("command"):
            
#             cmd_text = match.group("command")
            
#             submatch = command_decomposer.match(cmd_text)

#             if submatch:
#                 command = submatch.group("name")
#                 argument = submatch.group("content")
#             else:
#                 print("Unparsed command:", cmd_text)
#                 command = "unrecognized"
#         else: # it's math, so we can get the length of it directly
#             command = "math"
#         if command in allowed_commands:
#             # Calculate content positions in original text
#             prefix_len = len(match.group(0)) - len(argument) - 1
#             content_start = start + prefix_len
#             content_end = end - 1

#             # Mark command syntax as ignored
#             ignored_spans.extend([(start, content_start), (content_end, end)])
#             allowed_content_spans.append((content_start, content_end))

#             # Process content words
#             doc = nlp(argument)
#             for token in doc:
#                 if token.is_alpha and len(token.text) > 2:
#                     word_start = content_start + token.idx
#                     word_end = word_start + len(token.text)
#                     words_with_positions.append((word_start, word_end, token.text.lower()))

#             # Build cleaned text for sentence segmentation
#             cleaned_parts.extend([
#                 text[current_pos:start],
#                 ' ' * (content_start - start),  # Replace command prefix
#                 argument,
#                 ' ' * (end - content_end - 1)   # Replace command suffix
#             ])
#             current_pos = end
#         else:
#             # Ignore other commands entirely
#             ignored_spans.append((start, end))
#             cleaned_parts.append(text[current_pos:start] + ' ' * (end - start))
#             current_pos = end



#     # Step: Extend ignored_spans with trailing {...} blocks if they appear after an unallowed command

#     # This is necessary because with the regex I can't find a {} inside another one, so \h1{\textbf{jj}} would cause problems for example
#     i = 0
#     while i < len(ignored_spans):
#         span_start, span_end = ignored_spans[i]

#         # Skip whitespace to look for the next non-space character
#         j = span_end
#         while j < len(text) and text[j].isspace():
#             j += 1

#         # Check if next char is opening brace
#         if j < len(text) and text[j] == '{':
#             brace_start = j
#             depth = 1
#             j += 1
#             while j < len(text) and depth > 0:
#                 if text[j] == '{':
#                     depth += 1
#                 elif text[j] == '}':
#                     depth -= 1
#                 j += 1

#             if depth == 0:
#                 brace_end = j
#                 ignored_spans.append((brace_start, brace_end))

#         i += 1
#     all_ignored = sorted(ignored_spans)
    
#     index = 0
#     ignored_index = 0
#     while index < len(text):
#         if ignored_index < len(all_ignored):
#             curr_start, curr_end = all_ignored[ignored_index]
#         else:
#             # write what is remaining of the text and break
#             parts_to_analyze[index, len(text)] = text[index:len(text)]
#             break
#         if index < curr_start:
#             parts_to_analyze[index, curr_start] = text[index:curr_start]

#         parts_to_ignore[curr_start, curr_end] = text[curr_start:curr_end]
#         ignored_index+=1
#         index = curr_end
#     return parts_to_ignore, parts_to_analyze