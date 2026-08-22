import subprocess
import sys
import os
import shutil

def build_rust_engine():
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    rust_dir = os.path.join(repo_root, "rust_engine")
    
    print("[1/3] Compilando motor Rust via Cargo (Release)...")
    res = subprocess.run(["cargo", "build", "--release"], cwd=rust_dir)
    if res.returncode != 0:
        print("[ERRO] Falha na compilação do Rust via Cargo.")
        sys.exit(1)
        
    # Identifica o artefato gerado de acordo com o Sistema Operacional
    target_release = os.path.join(rust_dir, "target", "release")
    if sys.platform == "win32":
        built_lib = os.path.join(target_release, "concurse_core.dll")
        dest_pyd = os.path.join(repo_root, "concurse_core.pyd")
    elif sys.platform == "darwin":
        built_lib = os.path.join(target_release, "libconcurse_core.dylib")
        dest_pyd = os.path.join(repo_root, "concurse_core.so")
    else:
        built_lib = os.path.join(target_release, "libconcurse_core.so")
        dest_pyd = os.path.join(repo_root, "concurse_core.so")
        
    if not os.path.exists(built_lib):
        print(f"[ERRO] Biblioteca compilada não encontrada em: {built_lib}")
        sys.exit(1)
        
    print(f"[2/3] Copiando artefato para a raiz: {dest_pyd}...")
    shutil.copy(built_lib, dest_pyd)
    
    print("[3/3] Validando importação no Python...")
    sys.path.insert(0, repo_root)
    try:
        import concurse_core
        print("  OK! concurse_core importado com sucesso:")
        print("  Funcoes disponiveis:", [f for f in dir(concurse_core) if not f.startswith("__")])
        print("\nRebuild concluido com sucesso!")
    except Exception as e:
        print(f"[AVISO] Nao foi possivel importar concurse_core: {e}")

if __name__ == "__main__":
    build_rust_engine()
