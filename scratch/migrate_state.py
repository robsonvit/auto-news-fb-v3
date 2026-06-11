import json

with open('posted_ids.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

print(f'Formato atual: {type(data).__name__}')

if isinstance(data, list):
    novo = {"ids": data, "titles": []}
    with open('posted_ids.json', 'w', encoding='utf-8') as f:
        json.dump(novo, f, indent=2, ensure_ascii=False)
    print(f'Migrado com sucesso! {len(data)} IDs preservados.')
elif isinstance(data, dict):
    ids_count = len(data.get("ids", []))
    titles_count = len(data.get("titles", []))
    print(f'Ja esta no novo formato! IDs: {ids_count} | Titulos: {titles_count}')
