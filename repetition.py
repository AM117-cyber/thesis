import re
import sys
import spacy
from collections import defaultdict, Counter


from utils import mark_first_second_person_and_adject, mark_passive_voice, mark_weasel_spanglish, merge_dicts_by_start_order, separate_latex_commands

nlp = spacy.load("es_core_news_sm")

def process_latex_paragraph(text, ignore_words):
    '''Receives a paragraph that might contain latex commands or mathematic elements, which it ignores'''


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
            allowed_content_spans.append((content_start, end))

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

    # Add remaining text after last command
    cleaned_parts.append(text[current_pos:])
    cleaned_text = ''.join(cleaned_parts)

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
                segment = text[brace_start:brace_end]

        i += 1




    # Step 2: Process non-command text, excluding allowed content
    all_ignored = sorted(ignored_spans)
    allowed_intervals = []
    current_pos = 0


    for start, end in all_ignored:
        ignor = text[start:end]
        a = text[start]
        segment = text[current_pos:start]
        if current_pos < start:
            allowed_intervals.append((current_pos, start))

        current_pos = max(current_pos, end)
    if current_pos < len(text):
        allowed_intervals.append((current_pos, len(text)))

    for start, end in allowed_intervals:
        segment = text[start:end]
        doc = nlp(segment)
        for token in doc:
            if token.is_alpha and len(token.text) > 2:
                word_start = start + token.idx
                word_end = word_start + len(token.text)
                words_with_positions.append((word_start, word_end, token.text.lower()))

    # Step 3: Analyze word frequencies and sentences
    word_freq = defaultdict(int)
    for _, _, word in words_with_positions:
        word_freq[word] += 1

    # Map original positions to cleaned text for sentence alignment
    original_to_cleaned = []
    cleaned_pos = 0
    for i in range(len(text)):
        in_ignored = any(s <= i < e for s, e in all_ignored)
        original_to_cleaned.append(cleaned_pos if not in_ignored else None)
        if not in_ignored:
            cleaned_pos += 1
    # print("REACHING CLEAN TEXT MODIFICATION!!!!")
    # cleaned_text = mark_passive_voice(cleaned_text)

    # print(f'cleaned_text after passive markings: {cleaned_text}\n')
    # cleaned_text = mark_first_second_person_and_adject(cleaned_text)
    # print(f'cleaned_text after adje,1st,2nd: {cleaned_text}')
    # cleaned_text = mark_weasel_spanglish(weasel, spanglish, cleaned_text)
    # print(f'cleaned_text after spanglish: {cleaned_text}')

    # Segment sentences in cleaned text
    doc_cleaned = nlp(cleaned_text)
    sentence_spans = [(s.start_char, s.end_char) for s in doc_cleaned.sents]
    for start, end in sentence_spans:
        sentence = cleaned_text[start:end]
        print(sentence)

    # Track word counts per sentence
    word_sentence_counts = defaultdict(lambda: defaultdict(int))
    for start, _, word in words_with_positions:
        cleaned_start = original_to_cleaned[start]
        if cleaned_start is None:
            continue
        for sent_idx, (sent_start, sent_end) in enumerate(sentence_spans):
            if sent_start <= cleaned_start < sent_end:
                word_sentence_counts[word][sent_idx] += 1
                break

    # Determine words to highlight
    words_to_highlight = set()
    for word in word_freq:
        if word in ignore_words:
            continue
        if word_freq[word] > 2:
            words_to_highlight.add(word)
            continue  # Skip other checks if already highlighted

        # Check consecutive sentences
        sent_indices = sorted(word_sentence_counts[word].keys())
        for i in range(len(sent_indices) - 1):
            if sent_indices[i + 1] - sent_indices[i] == 1:
                words_to_highlight.add(word)
                break

        # Check same-sentence duplicates
        for count in word_sentence_counts[word].values():
            if count >= 2:
                words_to_highlight.add(word)
                break

    # Step 4: Apply highlights
    highlight_spans = []
    for start, end, word in words_with_positions:
        if word in words_to_highlight:
            highlight_spans.append((start, end))

    # Sort spans in reverse order to prevent overlap issues
    highlight_spans.sort(reverse=True, key=lambda x: x[0])
    modified_text = list(text)

    for start, end in highlight_spans:
        highlighted = r'\textcolor{green}' + ''.join(modified_text[start:end]) + ''
        modified_text[start:end] = list(highlighted)

    # with open("repeticiones.tex", "w", encoding="utf-8") as f:
    #     f.write(''.join(modified_text))

    # print("Modified file saved as:", "repeticiones.tex")


    return ''.join(modified_text)

# Rest of the code (main function, etc.) remains the same as previous solution



def process_latex_paragraph1(text, ignore_words):
    to_ignore, to_analyze = separate_latex_commands(text)
    paragraph = ""
    
    temp_separator = " \n "  # Unique string with non-word characters

    for value in to_analyze.values():
        paragraph += value + temp_separator
    
    colors = ['Green', 'Cerulean', 'red']
    paragraph = highlight_repeated_words_window(paragraph, colors, 200, ignore_words)
    # Split into parts using separator
    highlighted_parts = paragraph.split(temp_separator)
    
    # Update dictionary with highlighted parts
    for key, part in zip(to_analyze.keys(), highlighted_parts):
        to_analyze[key] = part  # Remove extra whitespace
    p = merge_dicts_by_start_order(to_ignore, to_analyze)
    return p


def highlight_repeated_words_window(text, color_list, window_size=100, ignore_words= None, long_sentence_limit = 15):
    if ignore_words is None:
        ignore_words = []
    # Normalize ignore_words to lower-case for case-insensitive comparison
    ignore_words_set = set(w.lower() for w in ignore_words)

    # Tokenize words and keep track of their positions (start, end in chars)
    words_with_pos = [
        (m.group(0), m.start(), m.end())
        for m in re.finditer(r'\b\w+\b', text)
    ]
    words_lower = [w[0].lower() for w in words_with_pos]

    # Define a filter function for valid words
    def is_valid(word):
        return len(word) > 2 and word not in ignore_words_set

    # Global frequency count (only valid words)
    filtered_words = [w for w in words_lower if is_valid(w)]
    word_global_count = Counter(filtered_words)

    # Find words repeated at least twice within any sliding window of size window_size (in chars)
    repeated_in_window = set()
    text_length = len(text)
    step = 1  # You can increase this for speed if needed

    for start in range(0, text_length - window_size + 1, step):
        end = start + window_size
        # Find words that are fully or partially within the window and valid
        window_words = [
            w[0].lower()
            for w in words_with_pos
            if (w[1] < end and w[2] > start) and is_valid(w[0].lower())
        ]
        window_count = Counter(window_words)
        for word, count in window_count.items():
            if count >= 2:
                repeated_in_window.add(word)

    # Combine with words appearing at least 3 times globally
    target_words = {w for w in word_global_count if word_global_count[w] >= 3 or w in repeated_in_window}
    # Assign colors cycling through the list
    color_map = {}
    word_index_map = {}
    for idx, word in enumerate((target_words)):
        color_map[word] = color_list[idx % len(color_list)]
        idx+=1
        word_index_map[word] = idx


    # Assign a unique index to each word in target_words (starting at 1)
    word_index_map = {word: idx + 1 for idx, word in enumerate((target_words))}

    
    
    # Function to replace words with highlighted version
    def replacer(match):
        word = match.group(0)
        word_lower = word.lower()
        if word_lower in color_map:
            color = color_map[word_lower]
            index = word_index_map[word_lower]
            return f"\\textcolor{{{color}}}{{[{word}$^{{{index}}}$]}}"
        else:
            return word
    
    # --- Long sentence detection and highlighting ---
    # Split text into sentences (handles ., !, ? followed by space or end of string)
    sentence_pattern = r'([^.!?]*[.!?]["\']?[ \t]*)'

    sentences = re.findall(sentence_pattern, text)
    highlighted_sentences = []

    for sentence in sentences:
        # Count valid words in this sentence
        sentence_words = [w.lower() for w in re.findall(r'\b\w+\b', sentence)]
        
        if len(sentence_words) > long_sentence_limit:
            # Wrap the entire sentence with a custom highlight (e.g., tcolorbox or custom macro)
            command = "{\color{Thistle} ["
            sentence = command + f"{{{sentence}}} " + "$^{largo}$]}"
        highlighted_sentences.append(sentence)

    # Reconstruct the text with long sentences marked
    marked_text = ''.join(highlighted_sentences)

    # Now apply repeated-word highlighting
    highlighted_text = re.sub(r'\b\w+\b', replacer, marked_text)
    return highlighted_text








latex_text = r"""\textbf{This} is a test sentence. sentence is just a test. The test is successful. The word test appears many fine times.\note{ Here} a lo mejor we have another paragraph\cite[abs]{old}. Another paragraph is red \sethlcolor{red}\hl{fine} remover. Paragraph repetition here is what cite means and \cite[abs]{rr} this paragraph does.Eres visto de múltiples y disímiles maneras. Tú, el que encuentra todo rápido."""





###############################################
################# WEASEL WORDS ################
weasels = [
    "a largo plazo", "a lo mejor", "a menudo", "a veces", "al parecer", 
    "muchos", "muchas", "diversos", "diversas", "muy", "bastante", 
    "varios", "varias", "extremadamente", "excesivamente", "notablemente", 
    "pocos", "poco", "sorprendentemente", "principalmente", "mayormente", 
    "en gran medida", "enorme", "minúsculo", "excelente", "significativo", 
    "significativa", "significativamente", "sustancial", "sustancialmente", 
    "claramente", "vasto", "relativamente", "completamente", "un", "una", 
    "unos", "unas", "cualquier", "alguno", "alguna", "algunos", "algunas", 
    "supuestamente", "aparentemente", "algo", "alguien", "básicamente", 
    "casi", "cerca de", "cosa", "demasiado", "en cierto modo", 
    "en cierto sentido", "en gran medida", "en la mayoría de los casos", 
    "en ocasiones", "en parte", "en principio", "en su mayoría", 
    "es posible que", "generalmente", "hay quienes dicen", "parece", 
    "más o menos", "por lo general", "quizá", "quizás", "se dice que", 
    "se estima que", "se podría decir que", "según se cree", 
    "la mayoría de la gente dice", "la mayoría de la gente piensa", 
    "los investigadores creen"
]

spanglish = ["parsear", "remover"]


# modified_paragraph = process_latex_paragraph(latex_text,["como","antes","bajo","contra", "the"],weasels, spanglish)

# print(modified_paragraph)
