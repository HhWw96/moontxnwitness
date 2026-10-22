///|
/// Fixed reviewed producer SQL. The AST generator independently checks these constants.
fn orm2_sql(name : String) -> String raise {
  match name {
    "relation" =>
      "SELECT c.oid,c.relkind,c.relrowsecurity,c.relforcerowsecurity,c.relpersistence\nFROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace\nWHERE n.nspname=%s AND c.relname=%s LIMIT 2"
    "locks" =>
      "SELECT mode,granted FROM pg_locks WHERE pid=pg_backend_pid() AND relation=%s AND mode='AccessExclusiveLock' LIMIT 2"
    "columns" =>
      "SELECT a.attname,format_type(a.atttypid,a.atttypmod),a.attnotnull,\na.attgenerated,a.attidentity,(d.oid IS NOT NULL)\nFROM pg_attribute a LEFT JOIN pg_attrdef d ON d.adrelid=a.attrelid AND d.adnum=a.attnum\nWHERE a.attrelid=%s AND a.attnum>0 AND NOT a.attisdropped ORDER BY a.attnum LIMIT 9"
    "constraints" =>
      "SELECT contype,conkey,convalidated,conenforced,condeferrable,condeferred,connoinherit\nFROM pg_constraint WHERE conrelid=%s ORDER BY contype,oid LIMIT 16"
    "triggers" =>
      "SELECT oid FROM pg_trigger WHERE tgrelid=%s AND NOT tgisinternal ORDER BY oid LIMIT 4"
    "indexes" =>
      "SELECT i.indisprimary,i.indisunique,i.indisvalid,i.indisready,i.indimmediate,\ni.indnkeyatts,i.indnatts,(i.indexprs IS NULL),(i.indpred IS NULL),am.amname,\nARRAY(SELECT a.attname FROM unnest(i.indkey::smallint[]) WITH ORDINALITY k(attnum,n)\n JOIN pg_attribute a ON a.attrelid=i.indrelid AND a.attnum=k.attnum ORDER BY k.n),\nARRAY(SELECT ns.nspname FROM unnest(i.indclass::oid[]) WITH ORDINALITY k(opclass,n)\n JOIN pg_opclass oc ON oc.oid=k.opclass JOIN pg_namespace ns ON ns.oid=oc.opcnamespace ORDER BY k.n),\nARRAY(SELECT COALESCE(c.collisdeterministic,true) FROM unnest(i.indcollation::oid[]) WITH ORDINALITY k(coll,n)\n LEFT JOIN pg_collation c ON c.oid=k.coll ORDER BY k.n)\nFROM pg_index i JOIN pg_class ic ON ic.oid=i.indexrelid JOIN pg_am am ON am.oid=ic.relam\nWHERE i.indrelid=%s ORDER BY i.indexrelid LIMIT 4"
    "unsafe" =>
      "SELECT\n(SELECT count(*) FROM pg_constraint WHERE contype='f' AND (conrelid=%s OR confrelid=%s)),\n(SELECT count(*) FROM pg_rewrite WHERE ev_class=%s),\n(SELECT count(*) FROM pg_inherits WHERE inhrelid=%s OR inhparent=%s),\n(SELECT count(*) FROM pg_attribute a JOIN pg_type t ON t.oid=a.atttypid JOIN pg_namespace n ON n.oid=t.typnamespace\n WHERE a.attrelid=%s AND a.attnum>0 AND NOT a.attisdropped AND (n.nspname<>'pg_catalog' OR t.typtype='d'))"
    "locale" =>
      "SELECT datcollate,datctype FROM pg_database WHERE datname=current_database()"
    "function_catalog" =>
      "SELECT n.nspname,p.proname,p.prosrc,p.prosecdef,p.provolatile,p.proconfig,p.pronargs,\np.prorettype::regtype::text,l.lanname FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace\nJOIN pg_language l ON l.oid=p.prolang WHERE p.oid=%s"
    "trigger_catalog" =>
      "SELECT tgfoid,tgtype,tgenabled,tgnargs,encode(tgargs,'hex'),tgisinternal,tgqual IS NULL FROM pg_trigger WHERE oid=%s AND tgrelid=%s"
    "function_oid" =>
      "SELECT p.oid FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname=%s AND p.proname=%s"
    "trigger_oid" => "SELECT oid FROM pg_trigger WHERE tgrelid=%s AND tgname=%s"
    _ => fail("Unknown fixed ORM control SQL")
  }
}
