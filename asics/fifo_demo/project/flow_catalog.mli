(** Pure checked project declaration; no elaboration, filesystem, Git or tools. *)
val create : unit -> Hardcaml_asic.Flow.Catalog.t Core.Or_error.t
val source_inputs : string list
