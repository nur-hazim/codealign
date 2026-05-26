import re
import argparse
import ntpath
from datetime import datetime
from pathlib import Path
from codealign import align, Alignment
from codealign.lang.c import parse as parse_c
from prompt_toolkit import prompt
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.validation import Validator, ValidationError


def clean_c_code(code: str) -> str:
    """Clean C code to remove unsupported constructs."""
    # Remove preprocessor directives that the parser doesn't handle
    lines = code.split('\n')
    filtered_lines = []
    skip_until_endif = False
    
    for line in lines:
        stripped = line.strip()
        
        # Skip #ifdef, #else, #endif, #ifndef directives
        if stripped.startswith('#ifdef') or stripped.startswith('#ifndef'):
            skip_until_endif = True
            continue
        elif stripped.startswith('#else'):
            skip_until_endif = not skip_until_endif
            continue
        elif stripped.startswith('#endif'):
            skip_until_endif = False
            continue
        elif skip_until_endif:
            continue
        # Keep other preprocessor directives like #include
        elif stripped.startswith('#'):
            filtered_lines.append(line)
        # Skip global variable declarations with initializers (esp. arrays/structs)
        elif re.match(r'^\s*(static\s+)?(const\s+)?\w+\s+\w+\s*\[\s*\d*\s*\]\s*=', line):
            continue
        elif re.match(r'^\s*static\s+const\s+\w+\s+\w+\s*\[\s*\]', line):
            continue
        else:
            filtered_lines.append(line)
    
    return '\n'.join(filtered_lines)


def extract_function_names(code: str) -> list[str]:
    """Extract function names from C code."""
    try:
        functions = parse_c(bytes(code, "utf8"))
        return [func.name for func in functions]
    except Exception as e:
        print(f"Warning: Could not parse functions: {e}")
        return []


def display_function_selection(ref_functions: list[str], cand_functions: list[str]) -> tuple[str, str]:
    """Display interactive function selection with reference on left, candidate on right."""
    print("\n" + "=" * 80)
    print("FUNCTION SELECTION")
    print("=" * 80, end="\n\n")
    
    # Display available functions
    max_len = max(len(ref_functions), len(cand_functions)) if ref_functions or cand_functions else 1
    print(f"{'REFERENCE' : <40} | {'CANDIDATE':<40}")
    print("-" * 80)
    
    for i in range(max_len):
        ref_func = ref_functions[i] if i < len(ref_functions) else ""
        cand_func = cand_functions[i] if i < len(cand_functions) else ""
        print(f"{ref_func : <40} | {cand_func:<40}")
    
    print("\n")
    
    # Prompt for reference function selection
    ref_completer = WordCompleter(ref_functions, ignore_case=True)
    ref_validator  = Validator.from_callable(
        lambda x: x in ref_functions,
        error_message="Please select a valid reference function from the list.",
        move_cursor_to_end=True
    )
    ref_function = prompt(
        "Select reference function: ",
        completer=ref_completer,
        complete_while_typing=True,
        validator=ref_validator
    )
    
    # Prompt for candidate function selection
    cand_completer = WordCompleter(cand_functions, ignore_case=True)
    cand_validator  = Validator.from_callable(
        lambda x: x in cand_functions,
        error_message="Please select a valid candidate function from the list.",
        move_cursor_to_end=True
    )
    cand_function = prompt(
        "Select candidate function: ",
        completer=cand_completer,
        complete_while_typing=True,
        validator=cand_validator
    )
    
    return ref_function, cand_function


def save_alignment_result(alignment: Alignment, ref_file: str, ref_func: str) -> str | None:
    """Save alignment result to file with formatted filename.
    
    Filename format: referencefilename_functionname_ddmmyy_hh-mm-ss.txt
    Prompts user for confirmation before saving.
    """
    # Extract reference filename without extension
    ref_filename = Path(ref_file).stem
    
    # Get current datetime
    now = datetime.now()
    timestamp = now.strftime("%d%m%y_%H-%M-%S")
    
    # Create output filename
    output_filename = f"{ref_filename}_{ref_func}_{timestamp}.txt"
    
    # Prompt user for confirmation
    print(f"\nProposed filename: {output_filename}")
    save_choice = prompt("Save this alignment result? (yes/no): ").lower().strip()
    
    if save_choice in ['yes', 'y']:
        # Save to file
        with open(output_filename, 'w') as f:
            f.write(str(alignment))
        return output_filename
    else:
        return None


def calculate_alignment_percentage(alignment: Alignment) -> float:
    """Calculate the percentage of candidate function that matches the reference function.
    
    Calculates: (number of aligned candidate instructions / total candidate instructions) * 100
    Returns a percentage from 0% to 100%.
    """
    # Count total candidate instructions
    total_candidate_instrs = 0
    aligned_candidate_instrs = 0
    
    # Iterate through alignment list
    for ref_instr, cand_instr in alignment.alignment_list:
        # Count all candidate instructions
        if cand_instr is not None:
            total_candidate_instrs += 1
            # If both reference and candidate exist, it's an aligned instruction
            if ref_instr is not None:
                aligned_candidate_instrs += 1
        # Also count reference-only instructions (unaligned on candidate side)
        elif ref_instr is not None:
            # This is a reference instruction with no candidate match
            pass
    
    # Calculate percentage
    if total_candidate_instrs == 0:
        return 0.0
    
    percentage = (aligned_candidate_instrs / total_candidate_instrs) * 100
    return percentage


def display_alignment_ir(alignment: Alignment) -> None:
    """Display IR representations side-by-side with alignment pairs.
    
    Shows reference function on left and candidate function on right,
    with alignment pairs from alignment.alignment_list.
    """
    print("\n" + "=" * 155)
    print("INSTRUCTION-LEVEL ALIGNMENT")
    print("=" * 155)
    
    # Display header
    print(f"{'REFERENCE' : <79} | {'CANDIDATE':<79}")
    print("-" * 155)
    
    # Iterate through alignment list
    for ref_instr, cand_instr in alignment.alignment_list:
        # Format reference instruction
        if ref_instr is None:
            ref_str = "❌"
        else:
            ref_str = str(ref_instr)
        
        # Format candidate instruction
        if cand_instr is None:
            cand_str = "❌"
        else:
            cand_str = str(cand_instr)
        
        # Handle long strings by wrapping/truncating for display
        # Split by newlines if they exist
        ref_lines = ref_str.split('\n')
        cand_lines = cand_str.split('\n')
        
        max_lines = max(len(ref_lines), len(cand_lines))
        
        for i in range(max_lines):
            ref_line = ref_lines[i] if i < len(ref_lines) else ""
            cand_line = cand_lines[i] if i < len(cand_lines) else ""
            
            # Truncate if too long
            ref_line = ref_line[:77] if len(ref_line) > 77 else ref_line
            cand_line = cand_line[:77] if len(cand_line) > 77 else cand_line
            
            print(f"{ref_line : <79} | {cand_line:<79}")
        
        print("-" * 155)


# Parse command line arguments
parser = argparse.ArgumentParser(description="Evaluate neural decompilers by computing equivalence between 2 C functions")
parser.add_argument("--ref", "-r", type=str, required=True,
                    help="Path to reference C file (original source code)")
parser.add_argument("--pred", "-p", type=str, required=True,
                    help="Path to candidate/prediction C file (neural decompiled code)")
args = parser.parse_args()
print("\n" + "=" * 80)
print("Welcome to Codealigner!")
print("=" * 80, end="\n\n")

# Read the files
try:
    with open(args.ref, 'r') as f:
        reference = f.read()
    print(f"Loaded reference file: {ntpath.basename(args.ref)}")
except FileNotFoundError:
    print(f"Error: Reference file not found: {ntpath.basename(args.ref)}")
    exit(1)

try:
    with open(args.pred, 'r') as f:
        prediction = f.read()
    print(f"Loaded candidate file: {ntpath.basename(args.pred)}")
except FileNotFoundError:
    print(f"Error: Candidate file not found: {ntpath.basename(args.pred)}")
    exit(1)

# Clean both codes
prediction = clean_c_code(prediction)
reference = clean_c_code(reference)

# Extract function names
ref_functions = extract_function_names(reference)
cand_functions = extract_function_names(prediction)

print(f"Found {len(ref_functions)} functions in reference")
print(f"Found {len(cand_functions)} functions in candidate")

# Interactive selection
ref_func, cand_func = display_function_selection(ref_functions, cand_functions)

print(f"\nAligning: reference.{ref_func}() <-> candidate.{cand_func}()")

# Perform alignment
alignment: Alignment = align(
    prediction,
    reference,
    'c',
    partial_loops=True,
    candidate_function=cand_func,
    reference_function=ref_func
)

# Display IR side-by-side
display_alignment_ir(alignment)

# Calculate and display alignment percentage
alignment_percentage = calculate_alignment_percentage(alignment)
print("\n" + "=" * 80)
print("ALIGNMENT STATISTICS")
print("=" * 80)
print(f"Candidate function match to reference: {alignment_percentage:.2f}%")
print("=" * 80)


# Save to file
output_file = save_alignment_result(alignment, args.ref, ref_func)
if output_file:
    print(f"\nResults saved to: {output_file}")
else:
    print("\nResults not saved.")
