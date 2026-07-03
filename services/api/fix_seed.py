path = "scripts/seed_part_a.py"
with open(path) as f:
    content = f.read()

old_block = '''        # Upsert roles using fixed role_ids
        role_by_name = {}
        for r in ROLES:
            role = Role(**r)
            db.add(role)
            await db.commit()
            await db.refresh(role)
            role_by_name[r["role_name"]] = role.role_id
            print(f"Ensured role {r['role_name']} -> id {role.role_id}")'''

new_block = '''        # Idempotent upsert roles: check by name first, reuse existing id if found
        role_by_name = {}
        for r in ROLES:
            existing = await db.execute(
                select(Role).where(Role.role_name == r["role_name"])
            )
            found = existing.scalar_one_or_none()
            if found:
                role_by_name[r["role_name"]] = found.role_id
                print(f"Role {r['role_name']} already exists -> id {found.role_id}")
                continue
            role = Role(
                role_name=r["role_name"],
                capture_label=r["capture_label"],
                permissions=r["permissions"],
            )
            db.add(role)
            await db.commit()
            await db.refresh(role)
            role_by_name[r["role_name"]] = role.role_id
            print(f"Created role {r['role_name']} -> id {role.role_id}")'''

if old_block not in content:
    print("PATTERN NOT FOUND - manual check needed")
else:
    content = content.replace(old_block, new_block)
    with open(path, "w") as f:
        f.write(content)
    print("Patched successfully")
