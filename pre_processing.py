from datetime import datetime
import os
import re
import spacy
import sys

from repetition import process_latex_paragraph, process_latex_paragraph1
from utils import LineType, NoteType, add_note, check_number, fix_cite_usage, format_latex_commands, get_begin_end_block, get_math_block, line_classifier, merge_dicts_by_start_order, process_section_chapter_declaration, remove_inline_comments, sanitize_preamble, separate_latex_commands
from utils import mark_first_second_person, mark_passive_voice, mark_weasel_spanglish


###############################################
################# WEASEL WORDS ################
weasels = [
    "a largo plazo", "a lo mejor", "a menudo", "a veces", "al parecer", 
    "muchos", "muchas", "diversos", "diversas", "muy", "bastante", 
    "varios", "varias", "extremadamente", "excesivamente", "notablemente", 
    "pocos", "poco", "sorprendentemente", "principalmente", "mayormente", 
    "en gran medida", "enorme", "minúsculo", "excelente", "significativo", 
    "significativa", "significativamente", "sustancial", "sustancialmente",
    "tradicionalmente", "claramente", "vasto", "relativamente", "completamente",
    "unos", "unas", "cualquier", "alguno", "alguna", "algunos", "algunas", "bueno", "malo", "regular",
    "supuestamente", "aparentemente", "algo", "alguien", "básicamente", 
    "casi", "cerca de", "cosa", "demasiado", "en cierto modo", 
    "en cierto sentido", "en gran medida", "en la mayoría de los casos", 
    "en ocasiones", "en parte", "en principio", "en su mayoría", 
    "es posible que", "generalmente", "hay quienes dicen", "parece", 
    "más o menos", "por lo general", "quizá", "quizás", "se dice que", 
    "se estima que", "se podría decir que", "según se cree", 
    "la mayoría de la gente dice", "la mayoría de la gente piensa", 

    
    "los investigadores creen", "para muchos", "creciente",
    "ha revolucionado",  "concisas"
]

spanglish = ["parsear", "remover", "fitness", "mapearse", "tag", "script"]



ignore_for_repetition = [
    # Articles
    "el", "la", "los", "las", "un", "una", "unos", "unas", "del", "al",
    
    # Prepositions
    "a", "ante", "bajo", "con", "contra", "de", "desde", "en", "entre", 
    "hacia", "hasta", "para", "por", "según", "sin", "so", "sobre", "tras",
    
    # Pronouns
    "yo", "tú", "él", "ella", "usted", "nosotros", "vosotros", "ellos", 
    "ellas", "ustedes", "me", "te", "se", "nos", "os", "le", "les", "lo", 
    "la", "los", "las", "mi", "tu", "su", "sus", "tus", "nuestro", "vuestro", "mío", "tuyo",
    
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
    "hoy", "ayer", "mañana", "año", "mes", "semana", "día", "hora", "vez",

    "más", "que", "mas", "qué"

]

amount_of_comments_for_new_page = 25

def process_tex_file():
    """Processes a LaTeX file to find errors in its writing."""

    # try:
    #     file_path = sys.argv[1]
    # except IndexError:
    #     print("Error: No se ha especificado el fichero de entrada.")
    #     sys.exit(1)

    # # Define the base directory for revisions
    # revisions_dir = "revisiones"

    # # Ensure the base directory exists
    # os.makedirs(revisions_dir, exist_ok=True)

    # # Get the current date in yyyy-mm-dd format
    # today = datetime.now().strftime("%Y-%m-%d")

    # # Create the path for today's folder inside revisiones
    # output_folder = os.path.join(revisions_dir, today)
    # os.makedirs(output_folder, exist_ok=True)  # Ensure the directory exists

    # # Determine output file name
    # if len(sys.argv) > 2:
    #     output_tex = os.path.join(output_folder, sys.argv[2])
    # else:
    #     base_name, ext = os.path.splitext(os.path.basename(file_path))
    #     output_base = f"{base_name}-revisado-{today}"
    #     output_ext = ext if ext else ".tex"
    #     output_tex = os.path.join(output_folder, f"{output_base}{output_ext}")

    #     # Ensure unique file name
    #     version = 1
    #     while os.path.exists(output_tex):
    #         output_tex = os.path.join(output_folder, f"{output_base}v{version}{output_ext}")
    #         version += 1



    file_path = "ejemplo1.tex"
    output_tex = "Dario.tex"


    new_tex = ""


    try:
        with open(file_path, 'r', encoding='utf-8') as file:

            tex_content = file.read().strip()

            my_commands = [r"\usepackage[dvipsnames]{xcolor}",r"\input{word-comments.tex}"]

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
            comments = 0

            new_preamble, conflict = sanitize_preamble(preamble, my_commands)
            if conflict:
                new_tex += "\n\\notaparaelautor{Algunos comandos antes de begin{document} fueron comentados por posibles conflictos}" + "\n"

            doc_content = remove_inline_comments(doc_content)
            doc_content = format_latex_commands(doc_content)
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
                    if not first_paragraph_flag and  "section" in line:
                        first_paragraph_flag = 1
                        note = add_note(NoteType.CHAPTER_MISSING_INTRO, "")
                        new_tex += note + line + "\n"
                    else:   
                        new_tex += line + "\n"
                elif line_type is LineType.COMMAND or line_type is LineType.IMAGE or line_type is LineType.COMMENT or line_type is LineType.BEGIN_BLOCK_START_END:
                    new_tex += line + "\n"
                elif line_type is LineType.PARAGRAPH:
                    # if it is classified as a paragraph then check the following lines to determine its extension
                    # it will be considered part of the same text until the line reached is blank or starts with \item or \colchunk
                    first_paragraph_flag = 1
                    while i < total_lines-1:
                        next_line = lines[i+1]
                        if len(next_line) > 0 and not next_line.startswith(r'\item') and not next_line.startswith(r'\colchunk'):
                            i +=1
                            line += " " + next_line
                        else:
                            break
                    line = fix_cite_usage(line)
                    to_ignore, to_analyze = separate_latex_commands(line)
                    for key, value in to_analyze.items():
                        # dentro de estos métodos vamos a aumentar el contador de comments
                        to_analyze[key], comments = mark_passive_voice(to_analyze[key], comments)
                        to_analyze[key], comments = mark_first_second_person(to_analyze[key], comments) # Separar cuando se encuentra 1ra, 2da persona o adjetivo
                        to_analyze[key], comments = mark_weasel_spanglish(weasels, spanglish, to_analyze[key], comments)


                    
                    line = merge_dicts_by_start_order(to_ignore, to_analyze)
                    # this method is not considering repeated words inside a comment when it should
                    p = process_latex_paragraph1(line, ignore_for_repetition)
                    # si en este punto los comments superan la cantidad por página entonces agregamos \newpage
                    new_tex += p + "\n"
                    if comments >= amount_of_comments_for_new_page:
                        new_tex += "\n\\notaparaelautor{Salto de línea para tener espacio para los comentarios.}\n\\newpage\n"
                        comments = 0
                else: # the line is the beginning of a block that doesn't need revision
                    block = ""
                    if "\\begin" in line:
                        # Detect begin blocks
                        block, i = get_begin_end_block(lines, i)
                    if line == "\[":
                        block, i = get_math_block(lines, i)
                    new_tex += block + "\n"
                i += 1
            # new_tex = check_ambiguity_and_transitions(new_tex)
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
# if __name__ == "__main__":  # Replace with your .tex file path
#     process_tex_file()



######################################################################################
################# PROBAR TODO Y LUEGO VER REFERENCIAS BIEN PUESTAS ###################





