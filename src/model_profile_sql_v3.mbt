///|
/// Reviewed exact SQL constants. Regenerate/check with experiments/model_profile_v3/generate_sql_constants.py.
fn model_ddl_v3(schema : String, is_list : Bool) -> Array[String] raise {
  let templates = if is_list {
    [
      "CREATE SCHEMA \"mtw_template_schema\"", "CREATE TABLE \"mtw_template_schema\".\"business\"(key text COLLATE \"C\" PRIMARY KEY,items jsonb NOT NULL)",
      "CREATE TABLE \"mtw_template_schema\".\"identities\"(id text COLLATE \"C\" PRIMARY KEY,key text NOT NULL REFERENCES \"mtw_template_schema\".\"business\"(key),value text NOT NULL)",
      "CREATE TABLE \"mtw_template_schema\".\"effects\"(key text NOT NULL,item jsonb NOT NULL,items jsonb NOT NULL)",
      "CREATE FUNCTION \"mtw_template_schema\".\"before\"() RETURNS trigger LANGUAGE plpgsql VOLATILE SECURITY INVOKER SET search_path=pg_catalog AS $model$BEGIN\nIF TG_OP<>'UPDATE' OR NEW.key IS DISTINCT FROM OLD.key OR jsonb_typeof(NEW.items)<>'array' OR jsonb_array_length(NEW.items)<>jsonb_array_length(OLD.items)+1 OR NEW.items- (jsonb_array_length(NEW.items)-1) IS DISTINCT FROM OLD.items THEN RAISE EXCEPTION 'only one append is supported'; END IF;\nIF jsonb_typeof(NEW.items->-1)<>'object' OR NOT (NEW.items->-1 ?& ARRAY['id','value']) OR (SELECT count(*) FROM jsonb_object_keys(NEW.items->-1))<>2 OR jsonb_typeof(NEW.items->-1->'id')<>'string' OR jsonb_typeof(NEW.items->-1->'value')<>'string' THEN RAISE EXCEPTION 'invalid append item'; END IF;\nINSERT INTO \"mtw_template_schema\".\"identities\"(id,key,value) VALUES(NEW.items->-1->>'id',NEW.key,NEW.items->-1->>'value');\nRETURN NEW; END$model$",
      "CREATE FUNCTION \"mtw_template_schema\".\"after\"() RETURNS trigger LANGUAGE plpgsql VOLATILE SECURITY INVOKER SET search_path=pg_catalog AS $model$BEGIN INSERT INTO \"mtw_template_schema\".\"effects\"(key,item,items) VALUES(NEW.key,NEW.items->-1,NEW.items); RETURN NEW; END$model$",
      "CREATE TRIGGER model_before BEFORE INSERT OR UPDATE OR DELETE ON \"mtw_template_schema\".\"business\" FOR EACH ROW EXECUTE FUNCTION \"mtw_template_schema\".\"before\"()",
      "CREATE TRIGGER model_after AFTER UPDATE ON \"mtw_template_schema\".\"business\" FOR EACH ROW EXECUTE FUNCTION \"mtw_template_schema\".\"after\"()",
    ]
  } else {
    [
      "CREATE SCHEMA \"mtw_template_schema\"", "CREATE TABLE \"mtw_template_schema\".\"business\"(id bigint PRIMARY KEY,balance bigint NOT NULL,active boolean NOT NULL,region text COLLATE \"C\" NOT NULL,version uuid NOT NULL)",
      "CREATE TABLE \"mtw_template_schema\".\"state\"(key bigint PRIMARY KEY,version uuid,present boolean NOT NULL)",
      "CREATE TABLE \"mtw_template_schema\".\"candidates\"(version uuid PRIMARY KEY,key bigint NOT NULL,predecessor uuid,action text NOT NULL,old_present boolean NOT NULL,new_present boolean NOT NULL,image jsonb)",
      "CREATE TABLE \"mtw_template_schema\".\"effects\"(LIKE \"mtw_template_schema\".\"candidates\" INCLUDING ALL)",
      "CREATE UNIQUE INDEX ON \"mtw_template_schema\".\"effects\"(predecessor) WHERE predecessor IS NOT NULL",
      "CREATE FUNCTION \"mtw_template_schema\".\"before\"() RETURNS trigger LANGUAGE plpgsql VOLATILE SECURITY INVOKER SET search_path=pg_catalog AS $model$DECLARE k bigint; p uuid; live boolean; v uuid; BEGIN\nIF TG_OP<>'DELETE' AND (NEW.id IS NULL OR NEW.balance IS NULL OR NEW.active IS NULL OR NEW.region IS NULL) THEN RETURN NEW; END IF;\nIF TG_OP='UPDATE' AND NEW.id IS DISTINCT FROM OLD.id THEN RAISE EXCEPTION 'primary key mutation'; END IF;\nk:=CASE WHEN TG_OP='DELETE' THEN OLD.id ELSE NEW.id END;\nSELECT version,present INTO p,live FROM \"mtw_template_schema\".\"state\" WHERE key=k FOR UPDATE;\nIF NOT FOUND THEN RAISE EXCEPTION 'key outside configured domain'; END IF;\nIF TG_OP<>'INSERT' AND (NOT live OR p IS DISTINCT FROM OLD.version) THEN RAISE EXCEPTION 'source mismatch'; END IF;\nv:=gen_random_uuid();\nINSERT INTO \"mtw_template_schema\".\"candidates\" VALUES(v,k,p,TG_OP,live,TG_OP<>'DELETE',CASE WHEN TG_OP='DELETE' THEN NULL ELSE jsonb_build_object('balance',NEW.balance::text,'active',NEW.active,'region',NEW.region) END);\nIF TG_OP='DELETE' THEN RETURN OLD; ELSE NEW.version:=v; RETURN NEW; END IF;\nEND$model$",
      "CREATE FUNCTION \"mtw_template_schema\".\"after\"() RETURNS trigger LANGUAGE plpgsql VOLATILE SECURITY INVOKER SET search_path=pg_catalog AS $model$DECLARE v uuid; c record; n integer; BEGIN\nv:=CASE WHEN TG_OP='DELETE' THEN \"mtw_template_schema\".\"delete_token\"(OLD.id,OLD.version) ELSE NEW.version END;\nSELECT * INTO c FROM \"mtw_template_schema\".\"candidates\" WHERE version=v;\nIF NOT FOUND OR c.action<>TG_OP OR c.key IS DISTINCT FROM (CASE WHEN TG_OP='DELETE' THEN OLD.id ELSE NEW.id END) OR c.image IS DISTINCT FROM (CASE WHEN TG_OP='DELETE' THEN NULL ELSE jsonb_build_object('balance',NEW.balance::text,'active',NEW.active,'region',NEW.region) END) THEN RAISE EXCEPTION 'actual effect mismatch'; END IF;\nIF TG_OP='INSERT' AND c.old_present THEN RAISE EXCEPTION 'insert presence mismatch'; END IF;\nUPDATE \"mtw_template_schema\".\"state\" SET version=v,present=(TG_OP<>'DELETE') WHERE key=c.key AND version IS NOT DISTINCT FROM c.predecessor AND present=c.old_present;\nGET DIAGNOSTICS n=ROW_COUNT; IF n<>1 THEN RAISE EXCEPTION 'effect state mismatch'; END IF;\nINSERT INTO \"mtw_template_schema\".\"effects\" SELECT * FROM \"mtw_template_schema\".\"candidates\" WHERE version=v;\nIF TG_OP='DELETE' THEN RETURN OLD; ELSE RETURN NEW; END IF;\nEND$model$",
      "CREATE FUNCTION \"mtw_template_schema\".\"predecessor\"(v uuid) RETURNS uuid LANGUAGE plpgsql VOLATILE SECURITY INVOKER SET search_path=pg_catalog AS $model$DECLARE n integer; p uuid; BEGIN SELECT count(*),min(predecessor::text)::uuid INTO n,p FROM \"mtw_template_schema\".\"candidates\" WHERE version=v; IF n<>1 THEN RAISE EXCEPTION 'predecessor not unique'; END IF; RETURN p; END$model$",
      "CREATE FUNCTION \"mtw_template_schema\".\"delete_token\"(k bigint,p uuid) RETURNS uuid LANGUAGE plpgsql VOLATILE SECURITY INVOKER SET search_path=pg_catalog AS $model$DECLARE n integer; v uuid; BEGIN SELECT count(*),min(version::text)::uuid INTO n,v FROM \"mtw_template_schema\".\"candidates\" WHERE key=k AND predecessor=p AND action='DELETE'; IF n<>1 THEN RAISE EXCEPTION 'delete not unique'; END IF; RETURN v; END$model$",
      "CREATE TRIGGER model_before BEFORE INSERT OR UPDATE OR DELETE ON \"mtw_template_schema\".\"business\" FOR EACH ROW EXECUTE FUNCTION \"mtw_template_schema\".\"before\"()",
      "CREATE TRIGGER model_after AFTER INSERT OR UPDATE OR DELETE ON \"mtw_template_schema\".\"business\" FOR EACH ROW EXECUTE FUNCTION \"mtw_template_schema\".\"after\"()",
    ]
  }
  templates.map(text => {
    text.replace_all(
      old="\"mtw_template_schema\"",
      new=v3_dislock_quote(schema),
    )
  })
}

///|
fn model_control_sql_v3(
  name : String,
  schema : String,
  is_list : Bool,
) -> String raise {
  let text = match (is_list, name) {
    (true, "lock") =>
      "LOCK TABLE \"mtw_template_schema\".\"business\",\"mtw_template_schema\".\"identities\",\"mtw_template_schema\".\"effects\" IN ACCESS EXCLUSIVE MODE"
    (true, "snapshot") =>
      "SELECT jsonb_build_object('key',key,'items',items) FROM \"mtw_template_schema\".\"business\" ORDER BY key"
    (true, "ledger") =>
      "SELECT jsonb_build_object('key',key,'item',item,'items',items) FROM \"mtw_template_schema\".\"effects\" ORDER BY key,jsonb_array_length(items)"
    (true, "state") =>
      "SELECT jsonb_build_object('id',id,'key',key,'value',value) FROM \"mtw_template_schema\".\"identities\" ORDER BY id"
    (true, "catalog") =>
      "SELECT jsonb_build_object('name',p.proname,'body',p.prosrc,'securityDefiner',p.prosecdef,'volatility',p.provolatile,'config',p.proconfig,'arguments',pg_get_function_identity_arguments(p.oid),'return',p.prorettype::regtype::text,'language',l.lanname) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace JOIN pg_language l ON l.oid=p.prolang WHERE n.nspname=%s ORDER BY p.proname"
    (true, "triggers") =>
      "SELECT jsonb_build_object('name',t.tgname,'function',p.proname,'type',t.tgtype,'enabled',t.tgenabled,'args',encode(t.tgargs,'hex'),'internal',t.tgisinternal,'noPredicate',t.tgqual IS NULL) FROM pg_trigger t JOIN pg_proc p ON p.oid=t.tgfoid WHERE t.tgrelid=%s::regclass ORDER BY t.tgname"
    (true, "locale") =>
      "SELECT jsonb_build_object('collate',datcollate,'ctype',datctype) FROM pg_database WHERE datname=current_database()"
    (false, "lock") =>
      "LOCK TABLE \"mtw_template_schema\".\"business\",\"mtw_template_schema\".\"state\",\"mtw_template_schema\".\"candidates\",\"mtw_template_schema\".\"effects\" IN ACCESS EXCLUSIVE MODE"
    (false, "snapshot") =>
      "SELECT jsonb_build_object('key',id::text,'version',version::text,'values',jsonb_build_object('balance',balance::text,'active',active,'region',region)) FROM \"mtw_template_schema\".\"business\" ORDER BY id"
    (false, "ledger") =>
      "SELECT jsonb_build_object('key',key::text,'version',version::text,'predecessor',predecessor::text,'action',action,'oldPresent',old_present,'newPresent',new_present,'values',image) FROM \"mtw_template_schema\".\"effects\" ORDER BY key,version"
    (false, "state") =>
      "SELECT jsonb_build_object('key',key::text,'version',version::text,'present',present) FROM \"mtw_template_schema\".\"state\" ORDER BY key"
    (false, "catalog") =>
      "SELECT jsonb_build_object('name',p.proname,'body',p.prosrc,'securityDefiner',p.prosecdef,'volatility',p.provolatile,'config',p.proconfig,'arguments',pg_get_function_identity_arguments(p.oid),'return',p.prorettype::regtype::text,'language',l.lanname) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace JOIN pg_language l ON l.oid=p.prolang WHERE n.nspname=%s ORDER BY p.proname"
    (false, "triggers") =>
      "SELECT jsonb_build_object('name',t.tgname,'function',p.proname,'type',t.tgtype,'enabled',t.tgenabled,'args',encode(t.tgargs,'hex'),'internal',t.tgisinternal,'noPredicate',t.tgqual IS NULL) FROM pg_trigger t JOIN pg_proc p ON p.oid=t.tgfoid WHERE t.tgrelid=%s::regclass ORDER BY t.tgname"
    (false, "locale") =>
      "SELECT jsonb_build_object('collate',datcollate,'ctype',datctype) FROM pg_database WHERE datname=current_database()"
    _ => fail("Unknown configured model control SQL")
  }
  text.replace_all(old="\"mtw_template_schema\"", new=v3_dislock_quote(schema))
}
