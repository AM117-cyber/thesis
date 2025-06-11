from datetime import datetime
import os
import re
import spacy
import sys
from fireworks.client import Fireworks
from dotenv import load_dotenv
            

from Supported_statements.LLM import Fireworks_Api
from Supported_statements.ambiguity_transitions import check_ambiguity_and_transitions
from repetition import process_latex_paragraph, process_latex_paragraph1
from utils import LineType, NoteType, add_chapter_note, add_note, add_section_note, check_number, fix_cite_usage, format_latex_commands, get_begin_end_block, get_math_block, insert_ambiguity_comment, line_classifier, merge_dicts_by_start_order, process_section_chapter_declaration, jump_inline_comments, sanitize_preamble, separate_latex_commands
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

load_dotenv()

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
    output_tex = "a.tex"


    new_tex = ""
    text_for_LLM = []
    line_mapper = {}
    line_count_for_LLM = 0
    og_line_count = 1

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
                og_line_count += 1
            doc_content = jump_inline_comments(doc_content)
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
                    og_line_count += 1
                    continue
                
                line_type = line_classifier(line)

                # Print results based on classification
                if line_type is LineType.SECTION or line_type is LineType.CHAPTER:
                    text_for_LLM.append(line + "\n")
                    line_mapper[line_count_for_LLM] = og_line_count
                    line_count_for_LLM += 1
                    line, line_notes = process_section_chapter_declaration(lines, i,weasels, spanglish)
                    if not first_paragraph_flag and  "section" in line:
                        line_mapper[line_count_for_LLM-1] = og_line_count + 2 # porque la nota para missing intro se pone antes de la línea, sumando dos líneas al contador
                        first_paragraph_flag = 1
                        note = add_note(NoteType.CHAPTER_MISSING_INTRO, "")
                        new_tex += note + line + line_notes + "\n"
                        tmp = (note + line).split("\n")
                        og_line_count += len((note + line + line_notes).split("\n"))# el último \n indica la línea en la que me voy a parar
                    else:   
                        og_line_count += len((line + line_notes).split("\n"))
                        
                        new_tex += line + line_notes + "\n"

                elif line_type is LineType.COMMAND or line_type is LineType.IMAGE or line_type is LineType.COMMENT or line_type is LineType.BEGIN_BLOCK_START_END:
                    new_tex += line + "\n"
                    og_line_count += 1
                elif line_type is LineType.PARAGRAPH:

                    # if it is classified as a paragraph then check the following lines to determine its extension
                    # it will be considered part of the same text until the line reached is blank or starts with \item or \colchunk or not a paragraph
                    first_paragraph_flag = 1
                    while i < total_lines-1:
                        next_line = lines[i+1]
                        if len(next_line) > 0 and line_classifier(next_line) is LineType.PARAGRAPH and not (next_line.strip().startswith(r'\item') or next_line.strip().startswith(r'\colchunk')):
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
                    p, for_LLM = process_latex_paragraph1(line, ignore_for_repetition)
                    line_mapper[line_count_for_LLM] = og_line_count
                    text_for_LLM.append(for_LLM + "\n")
                    line_count_for_LLM += 1
                    
                    # si en este punto los comments superan la cantidad por página entonces agregamos \newpage
                    new_tex += p + "\n"
                    og_line_count += len((p).split("\n"))
                    # if comments >= amount_of_comments_for_new_page:
                    #     new_tex += "\n\\notaparaelautor{Salto de línea para tener espacio para los comentarios.}\n\\newpage\n"
                    #     og_line_count += 3
                    #     comments = 0
                else: # the line is the beginning of a block that doesn't need revision
                    block = ""
                    if "\\begin" in line:
                        # Detect begin blocks
                        block, i = get_begin_end_block(lines, i)
                    if line == "\[":
                        block, i = get_math_block(lines, i)
                    new_tex += block + "\n"
                    og_line_count += len((block).split("\n"))
                    
                i += 1


            API_KEY = os.environ.get("FIREWORKS_API_KEY")
            API_MODEL = os.environ.get("FIREWORKS_MODEL")
            fw = Fireworks(api_key=API_KEY)  # Fixed variable name (was api_key)
            model_id = API_MODEL
            print("LINE MAPPER")
            for key in line_mapper.keys():
                print(f"{key}: value: {line_mapper[key]}")
            print(f"count is: {og_line_count}")
            fw_llm_client = Fireworks_Api(fw, model_id)
            ambiguity, transitions, introduction, logical_order = check_ambiguity_and_transitions(text_for_LLM, fw_llm_client, line_mapper)
            # ambiguity = {(10,1): "Razón"}
            for key in ambiguity.keys():
                new_tex = insert_ambiguity_comment(new_tex, key[0], key[1], ambiguity[key])
            for section in transitions.keys():
                new_tex = add_section_note(new_tex, section, transitions[section])
            if introduction:
                new_tex = add_chapter_note(new_tex, introduction)
            if logical_order:
                new_tex = add_chapter_note(new_tex, logical_order)
            # new_tex = insert_ambiguity_comment(new_tex, 10, 1, "Razón")



            new_tex_content = new_preamble + doc_begin + new_tex + "\n" + doc_end + post_doc
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





