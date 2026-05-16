import sys
import os

def move_functions(src_file, dst_file, functions_to_move):
    with open(src_file, 'r', encoding='utf-8') as f:
        src_lines = f.readlines()
    
    moving_lines = []
    new_src_lines = []
    
    current_function = None
    collecting = False
    
    for line in src_lines:
        if line.startswith('def '):
            fname = line.split('(')[0][4:].strip()
            if fname in functions_to_move:
                current_function = fname
                collecting = True
                moving_lines.append(line)
            else:
                collecting = False
                new_src_lines.append(line)
        elif collecting:
            moving_lines.append(line)
        else:
            new_src_lines.append(line)
            
    with open(src_file, 'w', encoding='utf-8') as f:
        f.writelines(new_src_lines)
        
    with open(dst_file, 'a', encoding='utf-8') as f:
        f.write('\n\n')
        f.writelines(moving_lines)

move_functions('app.py', 'ui_logic.py', ['normalize_regime_value', 'normalize_result_regime', 'sort_result_df', 'technical_cols'])
