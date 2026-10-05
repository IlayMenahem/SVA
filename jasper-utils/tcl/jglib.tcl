# jglib.tcl: helpers for JasperGold Tcl sessions (tested with Jasper 2024.06, Tcl 8.6).
#
# `jgu run` uploads this file and exports its path as JGU_LIB:
#     source $::env(JGU_LIB)
# Every machine-readable line starts with JGU_ so `jgu summary` can parse jg.log.
#
# Pitfalls these procs encode:
#   - Adding any assume/stopat clears proof results: declare lemmas, twins and rigid
#     constants before the first prove, and read statuses (jgu::snapshot) before adding more.
#   - Jasper's `clock` command shadows Tcl's: time with jgu::now_ms.
#   - set_proofgrid_max_jobs does not bind automatic engine mode: always name engines.
#   - set_proven_directive defaults to true, so properties proven in the same session
#     silently become assumptions; jgu::dag_init turns that off for honest per-node results.
#   - Undriven registers are free inputs on every cycle; jgu::rigid holds one constant.
#   - `info script` is empty under jg -tcl; locate files with jgu::script_dir.
#   - A comment line ending in a backslash continues onto the next line.

namespace eval jgu {
    variable records {}
    variable record_ids {}
    variable windows 0
}

proc jgu::env {name default} {
    if {[info exists ::env($name)] && $::env($name) ne ""} {
        return $::env($name)
    }
    return $default
}

proc jgu::now_ms {} {
    return [::tcl::clock::milliseconds]
}

# Absolute directory of the script jgu started ($JGU_TCL); `info script` is empty under jg -tcl.
proc jgu::script_dir {} {
    return [file dirname [file normalize [jgu::env JGU_TCL [info script]]]]
}

# Property name without the top task prefix "<embedded>::".
proc jgu::short {prop} {
    return [string map {<embedded>:: {}} $prop]
}

# One whitespace-free token for JGU_ lines ("-" when empty).
proc jgu::token {value} {
    set token [regsub -all {\s+} [string trim $value] _]
    if {$token eq ""} {
        return -
    }
    return $token
}

proc jgu::has_prefix {prefix name} {
    return [string equal -length [string length $prefix] $prefix $name]
}

# Cap proofgrid jobs (default $JGU_JOBS, else 2). Returns the cap.
proc jgu::caps {{jobs ""}} {
    if {$jobs eq ""} {
        set jobs [jgu::env JGU_JOBS 2]
    }
    set_proofgrid_max_jobs $jobs
    set_proofgrid_per_engine_max_jobs $jobs
    return $jobs
}

# Seconds as Jasper's time-limit syntax: 900 -> 900s; values with units pass through.
proc jgu::limit {seconds} {
    if {[string is integer -strict $seconds]} {
        return ${seconds}s
    }
    return $seconds
}

# Properties of one type (assert, assume, cover) whose short name matches a glob.
proc jgu::props {type {pattern *}} {
    set matching {}
    foreach prop [get_property_list -include [list type $type]] {
        if {[string match $pattern [jgu::short $prop]]} {
            lappend matching $prop
        }
    }
    return $matching
}

# One get_property_info field, or "" when Jasper has none for this property.
proc jgu::field {prop field} {
    if {[catch {get_property_info $prop -list $field} value]} {
        return ""
    }
    return $value
}

# assert or cover (or assume), as results.json expects.
proc jgu::kind {prop} {
    set type [jgu::field $prop type]
    if {$type ne ""} {
        return $type
    }
    foreach kind {assert cover assume} {
        if {[lsearch -exact [get_property_list -include [list type $kind]] $prop] >= 0} {
            return $kind
        }
    }
    return unknown
}

# The leading number of a Jasper time value such as "0.03 s", or "".
proc jgu::seconds {value} {
    if {[regexp {^\s*([0-9]+(\.[0-9]+)?)} $value -> number]} {
        return $number
    }
    return ""
}

# Prove props with the given engines and per-property limit in seconds;
# returns the elapsed wall seconds. Props proven in the same call may assume
# each other unless jgu::dag_init ran (set_proven_directive false).
proc jgu::prove {props engines limit_s} {
    set_engine_mode $engines
    set_prove_time_limit [jgu::limit $limit_s]
    set start [jgu::now_ms]
    ::prove -property $props
    return [format %.3f [expr {([jgu::now_ms] - $start) / 1000.0}]]
}

# One JGU_RESULT line per property.
proc jgu::report {tag props} {
    foreach prop $props {
        puts [format "JGU_RESULT tag=%s id=%s kind=%s status=%s engine=%s time_s=%s depth=%s" \
            [jgu::token $tag] [jgu::token [jgu::short $prop]] [jgu::kind $prop] \
            [jgu::token [get_status $prop]] [jgu::token [jgu::field $prop engine]] \
            [jgu::token [jgu::seconds [jgu::field $prop time]]] \
            [jgu::token [jgu::field $prop min_length]]]
    }
}

# Dict of short name -> status; take it before any change that clears results.
proc jgu::snapshot {props} {
    set statuses [dict create]
    foreach prop $props {
        dict set statuses [jgu::short $prop] [get_status $prop]
    }
    return $statuses
}

# Add one results.json entry. Each id may be recorded once.
proc jgu::record {id kind status engine assumed {time_s ""}} {
    variable records
    variable record_ids
    if {[lsearch -exact $record_ids $id] >= 0} {
        error "jgu::record: $id already recorded"
    }
    lappend record_ids $id
    lappend records [dict create id $id kind $kind status $status engine $engine \
        assumed $assumed time_s $time_s]
}

# Record a property's current status. engine is used when Jasper names no solving engine;
# assumed lists the ledger ids (lemmas and premises) that were enabled as assumptions.
proc jgu::record_prop {prop engine assumed {id ""}} {
    if {$id eq ""} {
        set id [jgu::short $prop]
    }
    set solver [jgu::field $prop engine]
    if {$solver eq ""} {
        set solver $engine
    }
    jgu::record $id [jgu::kind $prop] [get_status $prop] $solver $assumed \
        [jgu::seconds [jgu::field $prop time]]
}

proc jgu::json_string {text} {
    set escaped [string map {\\ \\\\ \" \\\" \n \\n \r \\r \t \\t} $text]
    return "\"[regsub -all {[\x00-\x1f]} $escaped {}]\""
}

proc jgu::json_list {items} {
    set strings {}
    foreach item $items {
        lappend strings [jgu::json_string $item]
    }
    return "\[[join $strings {, }]\]"
}

proc jgu::json_record {record} {
    set fields {}
    foreach key {id kind status engine} {
        lappend fields "[jgu::json_string $key]: [jgu::json_string [dict get $record $key]]"
    }
    lappend fields "\"assumed\": [jgu::json_list [dict get $record assumed]]"
    set time_s [dict get $record time_s]
    if {[string is double -strict $time_s]} {
        lappend fields "\"time_s\": $time_s"
    }
    return "\{[join $fields {, }]\}"
}

# The recorded entries as the results.json document that accelerate-sva-proofs reads.
proc jgu::results_json {} {
    variable records
    set entries {}
    foreach record $records {
        lappend entries "    [jgu::json_record $record]"
    }
    return "\{\"properties\": \[\n[join $entries ",\n"]\n\]\}\n"
}

proc jgu::write_results {{path results.json}} {
    set out [open $path w]
    puts -nonewline $out [jgu::results_json]
    close $out
    puts "JGU_RESULTS path=$path"
    return $path
}

# --- assume-guarantee DAG replay -------------------------------------------------

# No hidden lemmas: proven properties and engine invariants are not reused.
proc jgu::dag_init {} {
    set_proven_directive false
    set_prove_invariants_import off
}

proc jgu::twin {id} {
    return ${id}__twin
}

# Declare lemma id as an assert plus a disabled assume twin of the same expression.
# Declare every lemma before the first prove.
proc jgu::lemma {id expr} {
    assert -name $id $expr
    assume -name [jgu::twin $id] $expr
    assume -disable [jgu::twin $id]
    return $id
}

# Prove one node assuming only the twins of its dependency lemmas, record it, and
# disable the twins again. premises: ids of always-on assumptions to list as assumed.
# Returns the status.
proc jgu::prove_node {prop deps engine limit_s {id ""} {premises {}}} {
    foreach dep $deps {
        assume -enable [jgu::twin $dep]
    }
    jgu::prove [list $prop] [list $engine] $limit_s
    jgu::record_prop $prop $engine [concat $deps $premises] $id
    jgu::report node [list $prop]
    set status [get_status $prop]
    foreach dep $deps {
        assume -disable [jgu::twin $dep]
    }
    return $status
}

# --- environment helpers ---------------------------------------------------------

# Hold sig at one free value from the first checked cycle on. With cut=1 the signal
# is first cut (stopat), for driven signals. Returns the assumption name.
proc jgu::rigid {sig {cut 0}} {
    if {$cut} {
        stopat $sig
    }
    set name jgu_rigid_[regsub -all {[^A-Za-z0-9_]} $sig _]
    assume -name $name "##1 \$stable($sig)"
    return $name
}

# The automatically created precondition covers (<assert>:precondition*) of props.
proc jgu::precondition_covers {props} {
    set covers {}
    set all [get_property_list -include {type cover}]
    foreach prop $props {
        set prefix [jgu::short $prop]:precondition
        foreach cover $all {
            if {[jgu::has_prefix $prefix [jgu::short $cover]]} {
                lappend covers $cover
            }
        }
    }
    return $covers
}

# --- traces ------------------------------------------------------------------------

# Open the counterexample (assert) or witness (cover) of prop in a new batch window.
proc jgu::open_trace {prop} {
    variable windows
    set window jgu_trace[incr windows]
    if {[jgu::kind $prop] eq "cover"} {
        visualize -cover -property $prop -new_window $window -batch -silent
    } else {
        visualize -violation -property $prop -new_window $window -batch -silent
    }
    return $window
}

# Tab-separated table of signals per cycle (Jasper numbers trace cycles from 1) of prop's trace, written to path
# (or printed as JGU_TRACE lines when path is ""). Returns the trace length.
proc jgu::trace_table {prop signals {path ""}} {
    set window [jgu::open_trace $prop]
    set length [visualize -get_length -window $window]
    set rows [list [join [concat cycle $signals] \t]]
    for {set cycle 1} {$cycle <= $length} {incr cycle} {
        set row [list $cycle]
        foreach signal $signals {
            if {[catch {visualize -get_value $signal $cycle -radix hex -window $window} value]} {
                set value ?
            }
            lappend row $value
        }
        lappend rows [join $row \t]
    }
    if {$path eq ""} {
        foreach row $rows {
            puts "JGU_TRACE [jgu::short $prop]\t$row"
        }
    } else {
        set out [open $path w]
        puts $out [join $rows \n]
        close $out
    }
    return $length
}

# Save prop's trace as VCD (read it with `jgu vcd`).
proc jgu::save_vcd {prop path} {
    set window [jgu::open_trace $prop]
    visualize -save -vcd $path -window $window -force
    return $path
}

# Write results.json when anything was recorded, then leave Jasper.
proc jgu::finish {{path results.json}} {
    variable records
    if {[llength $records]} {
        jgu::write_results $path
    }
    puts "JGU_DONE"
    exit -force
}
