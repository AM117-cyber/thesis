from datetime import datetime
import os
import re
import spacy
import sys

from repetition import process_latex_paragraph, process_latex_paragraph1
from utils import LineType, NoteType, add_note, check_number, get_begin_end_block, line_classifier, merge_dicts_by_start_order, process_section_chapter_declaration, separate_latex_commands
from utils import mark_first_second_person_and_adject, mark_passive_voice, mark_weasel_spanglish


###############################################
################# WEASEL WORDS ################
weasels = [
    "a largo plazo", "a lo mejor", "a menudo", "a veces", "al parecer", 
    "muchos", "muchas", "diversos", "diversas", "muy", "bastante", 
    "varios", "varias", "extremadamente", "excesivamente", "notablemente", 
    "pocos", "poco", "sorprendentemente", "principalmente", "mayormente", 
    "en gran medida", "enorme", "minúsculo", "excelente", "significativo", 
    "significativa", "significativamente", "sustancial", "sustancialmente", 
    "claramente", "vasto", "relativamente", "completamente","unos", "unas", 
    "cualquier", "alguno", "alguna", "algunos", "algunas", "bueno", "malo", "regular",
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

spanglish = ["parsear", "remover", "fitness"]



ignore_for_repetition = [
    # Articles
    "el", "la", "los", "las", "un", "una", "unos", "unas",
    
    # Prepositions
    "a", "ante", "bajo", "con", "contra", "de", "desde", "en", "entre", 
    "hacia", "hasta", "para", "por", "según", "sin", "so", "sobre", "tras",
    
    # Pronouns
    "yo", "tú", "él", "ella", "usted", "nosotros", "vosotros", "ellos", 
    "ellas", "ustedes", "me", "te", "se", "nos", "os", "le", "les", "lo", 
    "la", "los", "las", "mi", "tu", "su", "nuestro", "vuestro", "mío", "tuyo",
    
    # Common conjunctions
    "y", "o", "u", "pero", "mas", "aunque", "como", "que", "si", "porque", 
    "pues", "aún", "así", "tan", "tanto", "cuando", "mientras", "donde",
    
    # Frequent adverbs
    "muy", "mucho", "poco", "bien", "mal", "mejor", "peor", "siempre", 
    "nunca", "también", "tampoco", "ya", "todavía", "aquí", "allí", "ahora", 
    "antes", "después", "luego", "pronto", "casi", "solo", "solamente",
    
    # Common verbs (present tense)
    "es", "son", "era", "fue", "ser", "estar", "tener", "haber", "hacer", 
    "poder", "decir", "ir", "ver", "dar", "saber", "querer", "llegar", 
    "dejar", "parecer", "seguir", "encontrar", "llamar", "venir", "pensar",
    
    # Other function words
    "este", "ese", "aquel", "esta", "esa", "aquella", "estos", "esos", 
    "aquellos", "esto", "eso", "aquello", "algo", "nada", "todo", "cada", 
    "quien", "cuál", "cuáles", "cuánto", "cuánta", "cuántos", "cuántas",
    
    # Time-related words
    "hoy", "ayer", "mañana", "año", "mes", "semana", "día", "hora", "vez"
]

def process_tex_file():
    """Processes a LaTeX file to find errors in its writing."""
    try:
        file_path = sys.argv[1]
    except IndexError:
        print("Error: No se ha especificado el fichero de entrada.")
        return

    # Comprobar si se pasa fichero de salida por argumento
    if len(sys.argv) > 2:
        output_tex = sys.argv[2]
    else:
        # Construir nombre de salida asegurando que no exista ya
        # Obtener nombre base y extensión del fichero de entrada
        base_name, ext = os.path.splitext(os.path.basename(file_path))

        # Obtener fecha actual en formato yyyy-mm-dd
        today = datetime.now().strftime("%Y-%m-%d")

        # Nombre base para el fichero de salida
        output_base = f"{base_name}-revisado-{today}"
        output_ext = ext if ext else ".tex"
        output_tex = output_base + output_ext
        version = 1
        while os.path.exists(output_tex):
            output_tex = f"{output_base}v{version}{output_ext}"
            version += 1


    # file_path = sys.argv[1]
    # output_tex = sys.argv[2]

    # file_path = "ejemplo1.tex"
    # output_tex = "a.tex"
    new_tex = ""


    try:
        with open(file_path, 'r', encoding='utf-8') as file:

            tex_content = file.read().strip()

            macro_definitions = r"""
\usepackage{stackengine}
\stackMath
\usepackage{soul}
\usepackage[dvipsnames]{xcolor}

\input{word-comments.tex}
"""

            doc_pattern = re.compile(r"(\\begin\{document\})(.*?)(\\end\{document\})", re.DOTALL)
            match = doc_pattern.search(tex_content)
            if not match:
                print("Error: Couldn't find both \\begin{document} and \\end{document} in the file.")
                sys.exit(1)

            preamble = tex_content[:match.start(1)]
            doc_begin = match.group(1)
            doc_content = match.group(2)
            doc_end = match.group(3)
            post_doc = tex_content[match.end(3):]

            new_preamble = preamble + macro_definitions


            # Now properly split into lines
            lines = doc_content.split('\n')  # Split on newlines
            lines = [line.rstrip('\n') for line in lines]  # Remove any trailing newlines
            
            total_lines = len(lines)
            i = 0
            first_paragraph_flag = 0

            while i < total_lines:
                line = lines[i]
                
                if not line.strip():  # Skip empty lines
                    i += 1
                    new_tex += "\n"
                    continue
                
                line_type = line_classifier(line)

                # Print results based on classification
                if line_type is LineType.SECTION or line_type is LineType.CHAPTER:
                    line = process_section_chapter_declaration(lines, i,weasels, spanglish)
                    if not first_paragraph_flag:
                        first_paragraph_flag = 1
                        note = add_note(NoteType.CHAPTER_MISSING_INTRO, "")
                        new_tex += note + line + "\n"
                    else:   
                        new_tex += line + "\n"
                elif line_type is LineType.COMMAND or line_type is LineType.IMAGE or line_type is LineType.COMMENT:
                    new_tex += line + "\n"
                elif line_type is LineType.PARAGRAPH:

                    first_paragraph_flag = 1
                    to_ignore, to_analyze = separate_latex_commands(line)
                    for key, value in to_analyze.items():
                        to_analyze[key] = mark_passive_voice(to_analyze[key])
                        to_analyze[key] = mark_first_second_person_and_adject(to_analyze[key]) # Separar cuando se encuentra 1ra, 2da persona o adjetivo
                        to_analyze[key] = mark_weasel_spanglish(weasels, spanglish, to_analyze[key])


                    
                    line = merge_dicts_by_start_order(to_ignore, to_analyze)
                    # this method is not considering repeated words inside a comment when it should
                    p = process_latex_paragraph1(line, ignore_for_repetition)
                    new_tex += p + "\n"
                else: # the line begins with \begin{} and its content doesn't need revision
                # Detect begin blocks
                    begin_end_block, i = get_begin_end_block(lines, i)
                    new_tex += begin_end_block + "\n"
                i += 1
            new_tex_content = new_preamble + doc_begin + new_tex + doc_end + post_doc
            with open(output_tex, "w", encoding="utf-8") as f:
                f.write(new_tex_content)

            print("Modified file saved as:", output_tex)



                
    
    except FileNotFoundError:
        print(f"Error: File '{file_path}' not found.")
    except Exception as e:
        print(f"Error processing file: {e}")

process_tex_file()
# Example usage
if __name__ == "__main__":  # Replace with your .tex file path
    process_tex_file()



######################################################################################
################# PROBAR TODO Y LUEGO VER REFERENCIAS BIEN PUESTAS ###################





