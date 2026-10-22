///|
/// Fixed source templates derived from pinned install.py AST, not supplied hashes.
fn orm_expected_function(schema : String, name : String) -> String raise {
  let state = "\"" + schema + "\".\"_mtw_orm_state\""
  let candidates = "\"" + schema + "\".\"_mtw_orm_candidates\""
  let effects = "\"" + schema + "\".\"_mtw_orm_effects\""
  let deleted_version = "\"" + schema + "\".\"_mtw_orm_deleted_version\""
  let old_image = "jsonb_build_object('id',OLD.\"id\"::text,'email',OLD.\"email\",'hashed_password',OLD.\"hashed_password\",'is_active',OLD.\"is_active\",'is_superuser',OLD.\"is_superuser\",'is_verified',OLD.\"is_verified\")"
  let new_image = "jsonb_build_object('id',NEW.\"id\"::text,'email',NEW.\"email\",'hashed_password',NEW.\"hashed_password\",'is_active',NEW.\"is_active\",'is_superuser',NEW.\"is_superuser\",'is_verified',NEW.\"is_verified\")"
  match name {
    "before" =>
      "\nDECLARE k text; previous uuid; was_present boolean; v uuid; old_data jsonb; new_data jsonb;\nBEGIN\n IF TG_OP<>'DELETE' THEN\n  IF NEW.id IS NULL OR NEW.email IS NULL OR NEW.hashed_password IS NULL OR NEW.is_active IS NULL OR NEW.is_superuser IS NULL OR NEW.is_verified IS NULL THEN RETURN NEW; END IF;\n  IF TG_OP='UPDATE' AND NEW.id IS DISTINCT FROM OLD.id THEN RAISE EXCEPTION 'ORM fixed UUID mutation unsupported'; END IF;\n  k:=NEW.id::text;\n ELSE k:=OLD.id::text; END IF;\n SELECT token,present INTO previous,was_present FROM " +
      state +
      " WHERE key=k FOR UPDATE;\n IF NOT FOUND THEN RAISE EXCEPTION 'ORM key outside controlled fixed domain'; END IF;\n IF TG_OP<>'INSERT' AND (NOT was_present OR previous IS DISTINCT FROM OLD.\"" +
      "_mtw_orm_version" +
      "\") THEN RAISE EXCEPTION 'ORM source chain mismatch'; END IF;\n v:=gen_random_uuid();\n old_data:=CASE WHEN TG_OP='INSERT' THEN NULL ELSE " +
      old_image +
      " END;\n new_data:=CASE WHEN TG_OP='DELETE' THEN NULL ELSE " +
      new_image +
      " END;\n INSERT INTO " +
      candidates +
      "(token,key,predecessor,action,old_present,new_present,old_image,new_image)\n VALUES(v,k,previous,TG_OP,was_present,TG_OP<>'DELETE',old_data,new_data);\n IF TG_OP='DELETE' THEN RETURN OLD; ELSE NEW.\"" +
      "_mtw_orm_version" +
      "\":=v; RETURN NEW; END IF;\nEND\n"
    "predecessor" =>
      "\nDECLARE v uuid; n integer;\nBEGIN\n SELECT count(*),min(predecessor::text)::uuid INTO n,v FROM " +
      candidates +
      " WHERE token=token_text::uuid;\n IF n<>1 THEN RAISE EXCEPTION 'ORM candidate predecessor not unique'; END IF;\n RETURN v;\nEND\n"
    "deleted_version" =>
      "\nDECLARE v uuid; n integer;\nBEGIN\n SELECT count(*),min(token::text)::uuid INTO n,v FROM " +
      candidates +
      "\n WHERE key=key_text AND predecessor=predecessor_text::uuid AND action='DELETE';\n IF n<>1 THEN RAISE EXCEPTION 'ORM delete candidate not unique'; END IF;\n RETURN v;\nEND\n"
    "after" =>
      "\nDECLARE k text; v uuid; candidate record; n integer; actual_image jsonb;\nBEGIN\n IF TG_OP='DELETE' THEN k:=OLD.id::text; v:=" +
      deleted_version +
      "(k,OLD.\"" +
      "_mtw_orm_version" +
      "\"::text); actual_image:=NULL;\n ELSE k:=NEW.id::text; v:=NEW.\"" +
      "_mtw_orm_version" +
      "\"; actual_image:=" +
      new_image +
      "; END IF;\n SELECT * INTO candidate FROM " +
      candidates +
      " WHERE token=v;\n IF NOT FOUND OR candidate.key IS DISTINCT FROM k OR candidate.action IS DISTINCT FROM TG_OP OR candidate.new_image IS DISTINCT FROM actual_image THEN RAISE EXCEPTION 'ORM actual effect candidate mismatch'; END IF;\n IF TG_OP='INSERT' AND candidate.old_present THEN RAISE EXCEPTION 'ORM insert source presence drift'; END IF;\n UPDATE " +
      state +
      " SET token=v,present=(TG_OP<>'DELETE'),image=actual_image\n WHERE key=k AND token=candidate.predecessor AND present=candidate.old_present;\n GET DIAGNOSTICS n=ROW_COUNT;\n IF n<>1 THEN RAISE EXCEPTION 'ORM actual effect chain mismatch'; END IF;\n INSERT INTO " +
      effects +
      " SELECT * FROM " +
      candidates +
      " WHERE token=v;\n IF TG_OP='DELETE' THEN RETURN OLD; ELSE RETURN NEW; END IF;\nEND\n"
    _ => fail("Unknown fixed ORM source helper")
  }
}
