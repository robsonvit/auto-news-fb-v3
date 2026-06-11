"""
Mescla os IDs do remoto com os locais e gera o novo formato unificado.
"""
import json, subprocess

# Pega o conteudo do arquivo remoto (origin/master)
result = subprocess.run(
    ["git", "show", "origin/master:posted_ids.json"],
    capture_output=True, text=True, encoding='utf-8'
)
remote_data = json.loads(result.stdout)

# Pega o conteudo local atual
with open("posted_ids.json", "r", encoding="utf-8") as f:
    local_data = json.load(f)

# Extrai IDs de ambos (formato legado ou novo)
if isinstance(remote_data, list):
    remote_ids = set(remote_data)
elif isinstance(remote_data, dict):
    remote_ids = set(remote_data.get("ids", []))
else:
    remote_ids = set()

if isinstance(local_data, list):
    local_ids = set(local_data)
elif isinstance(local_data, dict):
    local_ids = set(local_data.get("ids", []))
    local_titles = local_data.get("titles", [])
else:
    local_ids = set()
    local_titles = []

# Mesclar
all_ids = local_ids | remote_ids
print(f"IDs remotos: {len(remote_ids)}")
print(f"IDs locais: {len(local_ids)}")
print(f"IDs mesclados: {len(all_ids)}")

# Salva no novo formato
novo = {
    "ids": sorted(list(all_ids)),
    "titles": local_titles  # Mantém títulos recentes do local
}

with open("posted_ids.json", "w", encoding="utf-8") as f:
    json.dump(novo, f, indent=2, ensure_ascii=False)

print("Salvo! Novo formato com", len(all_ids), "IDs e", len(local_titles), "titulos.")
