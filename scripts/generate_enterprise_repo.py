import os
import random
import string

def generate_random_string(length):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

def generate_file(path, content_size):
    with open(path, 'w') as f:
        f.write(generate_random_string(content_size))

def generate_binary_file(path, size_mb):
    with open(path, 'wb') as f:
        f.write(os.urandom(size_mb * 1024 * 1024))

def create_structure(base_dir, modules, files_per_module, max_depth):
    os.makedirs(base_dir, exist_ok=True)
    
    # Large binary files
    bin_dir = os.path.join(base_dir, 'assets_bin')
    os.makedirs(bin_dir, exist_ok=True)
    for i in range(5):
        generate_binary_file(os.path.join(bin_dir, f'data_{i}.bin'), random.randint(10, 50))

    total_files = 0
    for module in modules:
        module_path = os.path.join(base_dir, module)
        os.makedirs(module_path, exist_ok=True)
        
        for i in range(files_per_module):
            # Create deep nesting occasionally
            depth = random.randint(1, max_depth)
            curr_dir = module_path
            for d in range(depth):
                curr_dir = os.path.join(curr_dir, f'subdir_{d}')
                os.makedirs(curr_dir, exist_ok=True)
            
            file_name = f'file_{i}.txt'
            generate_file(os.path.join(curr_dir, file_name), 100)
            total_files += 1
            if total_files % 5000 == 0:
                print(f"Generated {total_files} files...")

if __name__ == "__main__":
    target_dir = os.getcwd()
    modules = ['frontend', 'backend', 'mobile', 'infrastructure', 'ai']
    files_per_module = 10100 # Total 50,500
    max_depth = 55
    print(f"Generating repository structure in {target_dir}...")
    create_structure(target_dir, modules, files_per_module, max_depth)
    print("Generation complete.")
