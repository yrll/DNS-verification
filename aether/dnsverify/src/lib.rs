mod lec;
mod record;
pub mod utils;
mod zonefile_parser;

use chrono::prelude::*;
use lec::LECManager;
use record::Record;
use rayon::prelude::*;
use std::collections::{HashMap, HashSet};
use std::io::Write;
use std::path::Path;
use std::str::FromStr;
use zonefile_parser::parse;

type Domain = Vec<String>;

type PureRecords = Vec<record::Record>;
type FPath = String;
type NS = String;
type ZoneFile = (FPath, NS, Domain);
type PureNSMap = HashMap<NS, Vec<(FPath, Domain, PureRecords)>>;

#[derive(Debug, Clone)]
pub struct UpdateSpec {
    pub file_name: String,
    pub add_rrs: Vec<Record>,
    pub del_rrs: Vec<Record>,
}

#[derive(Clone)]
pub struct Config {
    pub max_query_depth: usize,
    pub min_label_bits: usize,
    pub min_label_num: usize,
    pub redundant_bits: usize,
    pub redundant_labels: usize,
    pub label_encoding: LabelEncodingMode,
    pub label_bit_policy: LabelBitPolicy,
    pub label_cube_cache: bool,
    pub bdd_apply_cache_capacity: usize,
    pub bdd_profile: bool,
    pub bdd_threads: usize,
    pub rayon_threads: usize,
    pub lec_build_mode: LecBuildMode,
    pub bdd_cache: bool,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum LabelBitPolicy {
    Auto,
    Reserved,
    Compact,
}

impl LabelBitPolicy {
    pub fn resolve(self, full_only: bool) -> Self {
        match self {
            Self::Auto if full_only => Self::Compact,
            Self::Auto => Self::Reserved,
            policy => policy,
        }
    }
}

impl FromStr for LabelBitPolicy {
    type Err = String;

    fn from_str(value: &str) -> Result<Self, Self::Err> {
        match value {
            "auto" => Ok(Self::Auto),
            "reserved" => Ok(Self::Reserved),
            "compact" => Ok(Self::Compact),
            _ => Err(format!("invalid label bit policy: {value}")),
        }
    }
}

impl std::fmt::Display for LabelBitPolicy {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Auto => write!(f, "auto"),
            Self::Reserved => write!(f, "reserved"),
            Self::Compact => write!(f, "compact"),
        }
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum LabelEncodingMode {
    Shared,
    PerLayer,
}

impl FromStr for LabelEncodingMode {
    type Err = String;

    fn from_str(value: &str) -> Result<Self, Self::Err> {
        match value {
            "shared" => Ok(Self::Shared),
            "per-layer" => Ok(Self::PerLayer),
            _ => Err(format!("invalid label encoding mode: {value}")),
        }
    }
}

impl std::fmt::Display for LabelEncodingMode {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Shared => write!(f, "shared"),
            Self::PerLayer => write!(f, "per-layer"),
        }
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum LecBuildMode {
    Serial,
    Parallel,
}

impl FromStr for LecBuildMode {
    type Err = String;

    fn from_str(value: &str) -> Result<Self, Self::Err> {
        match value {
            "serial" => Ok(Self::Serial),
            "parallel" => Ok(Self::Parallel),
            _ => Err(format!("invalid LEC build mode: {value}")),
        }
    }
}

impl std::fmt::Display for LecBuildMode {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Serial => write!(f, "serial"),
            Self::Parallel => write!(f, "parallel"),
        }
    }
}

#[derive(Clone)]
pub struct RunOptions {
    pub config: Config,
    pub no_random_update: bool,
    pub full_only: bool,
    pub repeat: usize,
    pub dump_traces: bool,
}

impl Default for RunOptions {
    fn default() -> Self {
        RunOptions {
            config: Config {
                max_query_depth: 10,
                min_label_bits: 4,
                min_label_num: 5,
                redundant_bits: 1,
                redundant_labels: 1,
                label_encoding: LabelEncodingMode::Shared,
                label_bit_policy: LabelBitPolicy::Reserved,
                label_cube_cache: true,
                bdd_apply_cache_capacity: 1_000_000,
                bdd_profile: false,
                bdd_threads: 1,
                rayon_threads: 1,
                lec_build_mode: LecBuildMode::Serial,
                bdd_cache: true,
            },
            no_random_update: false,
            full_only: false,
            repeat: 1,
            dump_traces: true,
        }
    }
}

pub fn run(
    top_ns: Vec<String>,
    zonefiles: Vec<ZoneFile>,
    zone: &str,
    jobs: &HashSet<String>,
    out: &mut csv::Writer<std::fs::File>,
    mut zone_stats_out: Option<&mut csv::Writer<std::fs::File>>,
    trace_fp: &mut std::fs::File,
    update_spec: Option<UpdateSpec>,
    options: &RunOptions,
) {
    log::info!("Zone: {}", zone);
    log::debug!("Running with top_ns: {:?}", top_ns);
    log::debug!("Number of zonefiles: {}", zonefiles.len());
    log::debug!("Jobs: {:?}", jobs);
    log::debug!("Output file: {:?}", out.get_ref());
    log::debug!("Trace file: {:?}", trace_fp);

    let start = Utc::now();
    let ns2zones = match read_zonefiles(zonefiles) {
        Ok(ns2zones) => ns2zones,
        Err(_) => return,
    };
    let iot = get_duration(start);
    log::info!("Number of NS: {}", ns2zones.len());
    log::info!("Read zonefiles and parsed records cost: {}ms", iot);

    let accepted_input_rr_counts = ns2zones
        .iter()
        .flat_map(|(nameserver, zones)| {
            zones.iter().map(move |(fpath, _, records)| {
                ((nameserver.clone(), fpath.clone()), records.len())
            })
        })
        .collect::<HashMap<_, _>>();
    let accepted_input_rr_count = accepted_input_rr_counts.values().sum::<usize>();

    let canonical_ns2zones = ns2zones.clone();
    let start = Utc::now();
    let mut lec_manager = if options.full_only {
        LECManager::new_full_only(ns2zones, options.config.clone())
    } else {
        LECManager::new(ns2zones, options.config.clone())
    };
    let ct = get_duration(start);
    let construction_stats = lec_manager.construction_stats();
    let zone_aggregation_stats = lec_manager.zone_aggregation_stats(&accepted_input_rr_counts);
    let grouped_rule_count = zone_aggregation_stats
        .iter()
        .map(|stats| stats.grouped_rule_count)
        .sum::<usize>();
    let record_lec_count = zone_aggregation_stats
        .iter()
        .map(|stats| stats.record_lec_count)
        .sum::<usize>();
    let synthetic_refuse_count = zone_aggregation_stats
        .iter()
        .map(|stats| stats.synthetic_refuse_count)
        .sum::<usize>();
    let total_lec_count = record_lec_count + synthetic_refuse_count;
    if let Some(writer) = zone_stats_out.as_deref_mut() {
        for stats in &zone_aggregation_stats {
            let record_lec_ratio = ratio(stats.record_lec_count, stats.accepted_input_rr_count);
            let total_table_ratio = ratio(stats.total_lec_count, stats.accepted_input_rr_count);
            writer
                .write_record([
                    zone,
                    &stats.nameserver,
                    &stats.zone_file,
                    &stats.origin,
                    &stats.accepted_input_rr_count.to_string(),
                    &stats.grouped_rule_count.to_string(),
                    &stats.record_lec_count.to_string(),
                    &stats.synthetic_refuse_count.to_string(),
                    &stats.total_lec_count.to_string(),
                    &record_lec_ratio,
                    &total_table_ratio,
                ])
                .unwrap();
        }
        writer.flush().unwrap();
    }
    log::info!("Construction time: {}ms", ct);
    if options.dump_traces {
        writeln!(trace_fp, "===== INITIAL LEC STATE =====").unwrap();
        lec_manager.dump_lecs(trace_fp).unwrap();
    }

    let start = Utc::now();
    let mut tl_mgr = lec_manager.symbolic_exec_par(None, &top_ns);
    let se = get_duration(start);
    log::info!("Symbolic execution time: {}ms", se);

    let start = Utc::now();
    let initial_errors = lec_manager.property_checking(&tl_mgr, jobs);
    let pc = get_duration(start);
    log::info!("Property checking time: {}ms", pc);
    let lec_semantic_hash = lec_manager.lec_semantic_hash();
    let trace_semantic_hash = lec_manager.trace_semantic_hash(&tl_mgr);
    if options.dump_traces {
        lec_manager
            .dump_traces(trace_fp, &tl_mgr, None, "INITIAL TRACE STORE")
            .unwrap();
    }

    let zone_file_count = lec_manager.num_zonefiles();
    let rr_count = lec_manager.num_records();
    let trace_count = tl_mgr.get_num_traces();
    let log_count = tl_mgr.get_num_logs();

    let (
        rct,
        rse,
        rpc,
        incremental_property_pass,
        incremental_error_text,
        affected_trace_count,
        update_add_count,
        update_del_count,
        update_type,
        encoding_rebuild_required,
        incremental_fallback_full_rebuild,
        fallback_reason,
    ) = if options.full_only {
        (
            String::new(),
            String::new(),
            String::new(),
            String::new(),
            String::new(),
            0,
            0,
            0,
            "NONE".to_string(),
            false,
            false,
            String::new(),
        )
    } else {
        let (ns, zid, add_rrs, del_rrs, update_type) = match update_spec {
            Some(spec) => {
                let (ns, zid) = lec_manager
                    .find_zonefile_by_name(&spec.file_name)
                    .unwrap_or_else(|| panic!("update zone file not found: {}", spec.file_name));
                log::info!(
                    "Apply external update with {} add_rrs and {} del_rrs for zonefile {}",
                    spec.add_rrs.len(),
                    spec.del_rrs.len(),
                    spec.file_name
                );
                let update_type = infer_update_type(&spec.add_rrs, &spec.del_rrs);
                (ns, zid, spec.add_rrs, spec.del_rrs, update_type)
            }
            None => {
                if options.no_random_update {
                    panic!("--no-random-update requires --updates");
                }
                let (ns, zid, add_rrs, del_rrs) = lec_manager.random_choose(&top_ns);
                log::info!(
                    "Randomly generate {} add_rrs and {} del_rrs for zonefile {}",
                    add_rrs.len(),
                    del_rrs.len(),
                    lec_manager.get_zonefile_bdd_ref(&ns, zid).unwrap().fpath()
                );
                let update_type = infer_update_type(&add_rrs, &del_rrs);
                (ns, zid, add_rrs, del_rrs, update_type)
            }
        };
        let update_add_count = add_rrs.len();
        let update_del_count = del_rrs.len();
        let update_fpath = lec_manager
            .get_zonefile_bdd_ref(&ns, zid)
            .unwrap()
            .fpath()
            .to_string();
        let add_for_rebuild = add_rrs.clone();
        let del_for_rebuild = del_rrs.clone();
        let update_start = Utc::now();
        match lec_manager.update_zonefile_rrs(&ns, zid, add_rrs, del_rrs) {
            Ok(()) => {
                let rct = get_duration(update_start);
                log::info!("Reconstruction time: {}ms", rct);
                if options.dump_traces {
                    writeln!(trace_fp, "===== UPDATED LEC STATE =====").unwrap();
                    lec_manager.dump_lecs(trace_fp).unwrap();
                }

                let start = Utc::now();
                let trace_indices =
                    lec_manager.inc_symbolic_exec_zonefile_par(&ns, zid, &mut tl_mgr);
                let affected_trace_count = trace_indices.len();
                let rse = get_duration(start);
                log::info!("Re-Symbolic execution time: {}ms", rse);
                let start = Utc::now();
                let incremental_errors =
                    lec_manager.inc_property_checking(&tl_mgr, trace_indices, jobs);
                let rpc = get_duration(start);
                (
                    rct.to_string(),
                    rse.to_string(),
                    rpc.to_string(),
                    incremental_errors.is_empty().to_string(),
                    incremental_errors.into_iter().collect::<Vec<_>>().join("|"),
                    affected_trace_count,
                    update_add_count,
                    update_del_count,
                    update_type,
                    false,
                    false,
                    String::new(),
                )
            }
            Err(reason) => {
                log::info!("Encoding rebuild required: {}", reason);
                let mut rebuilt_input = canonical_ns2zones.clone();
                apply_update_to_canonical(
                    &mut rebuilt_input,
                    &ns,
                    &update_fpath,
                    &add_for_rebuild,
                    &del_for_rebuild,
                );
                lec_manager = LECManager::new(rebuilt_input, options.config.clone());
                let rct = get_duration(update_start);
                let start = Utc::now();
                tl_mgr = lec_manager.symbolic_exec_par(None, &top_ns);
                let rse = get_duration(start);
                let affected_trace_count = tl_mgr.get_num_traces();
                let start = Utc::now();
                let incremental_errors = lec_manager.property_checking(&tl_mgr, jobs);
                let rpc = get_duration(start);
                (
                    rct.to_string(),
                    rse.to_string(),
                    rpc.to_string(),
                    incremental_errors.is_empty().to_string(),
                    incremental_errors.join("|"),
                    affected_trace_count,
                    update_add_count,
                    update_del_count,
                    update_type,
                    true,
                    true,
                    reason,
                )
            }
        }
    };

    log::info!("");
    out.write_record([
        zone,
        &lec_manager.num_lec().to_string(),
        &iot.to_string(),
        &ct.to_string(),
        &se.to_string(),
        &pc.to_string(),
        &rct,
        &rse,
        &rpc,
        &jobs.iter().cloned().collect::<Vec<_>>().join("|"),
        &(initial_errors.is_empty()).to_string(),
        &initial_errors.join("|"),
        &incremental_property_pass,
        &incremental_error_text,
        &rr_count.to_string(),
        &zone_file_count.to_string(),
        &trace_count.to_string(),
        &log_count.to_string(),
        &affected_trace_count.to_string(),
        &update_add_count.to_string(),
        &update_del_count.to_string(),
        &update_type,
        &encoding_rebuild_required.to_string(),
        &incremental_fallback_full_rebuild.to_string(),
        &fallback_reason,
        &options.config.max_query_depth.to_string(),
        &options.config.min_label_num.to_string(),
        &options.config.min_label_bits.to_string(),
        &options.config.label_encoding.to_string(),
        &options.config.label_bit_policy.to_string(),
        &options.config.label_cube_cache.to_string(),
        &options.config.bdd_apply_cache_capacity.to_string(),
        &options.config.bdd_profile.to_string(),
        &options.config.bdd_threads.to_string(),
        &options.config.rayon_threads.to_string(),
        &options.config.lec_build_mode.to_string(),
        &options.config.bdd_cache.to_string(),
        &construction_stats.preprocess_ms.to_string(),
        &construction_stats.bdd_setup_ms.to_string(),
        &construction_stats.lec_build_ms.to_string(),
        &construction_stats.label_level_count.to_string(),
        &construction_stats.unique_label_table_count.to_string(),
        &construction_stats.label_value_count_min.to_string(),
        &construction_stats.label_value_count_max.to_string(),
        &construction_stats.label_bits_min.to_string(),
        &construction_stats.label_bits_max.to_string(),
        &construction_stats
            .label_bits_by_level
            .iter()
            .map(|value| value.to_string())
            .collect::<Vec<_>>()
            .join("|"),
        &construction_stats
            .label_values_by_level
            .iter()
            .map(|value| value.to_string())
            .collect::<Vec<_>>()
            .join("|"),
        &construction_stats
            .shared_label_tail_start
            .map(|value| value.to_string())
            .unwrap_or_default(),
        &construction_stats.name_bits.to_string(),
        &construction_stats.rtype_count.to_string(),
        &construction_stats.rtype_bits.to_string(),
        &construction_stats.total_bits.to_string(),
        &construction_stats.compact_total_bits.to_string(),
        &construction_stats.bdd_variable_count.to_string(),
        &construction_stats.bdd_node_count.to_string(),
        &construction_stats.retained_record_hit_count.to_string(),
        &construction_stats.cache_hits.to_string(),
        &construction_stats.cache_misses.to_string(),
        &construction_stats.label_cube_cache_hits.to_string(),
        &construction_stats.label_cube_cache_misses.to_string(),
        &construction_stats.query_encode_calls.to_string(),
        &construction_stats.lec_query_encoding_ms.to_string(),
        &construction_stats.lec_record_partition_ms.to_string(),
        &construction_stats.lec_zone_ns_union_ms.to_string(),
        &peak_rss_kb().to_string(),
        &(std::env::var("RUST_MIN_STACK")
            .ok()
            .and_then(|value| value.parse::<usize>().ok())
            .unwrap_or(0)
            .div_ceil(1024 * 1024))
            .to_string(),
        &options.full_only.to_string(),
        &accepted_input_rr_count.to_string(),
        &grouped_rule_count.to_string(),
        &record_lec_count.to_string(),
        &synthetic_refuse_count.to_string(),
        &total_lec_count.to_string(),
        &lec_semantic_hash,
        &trace_semantic_hash,
    ])
    .unwrap();
}

fn ratio(numerator: usize, denominator: usize) -> String {
    if denominator == 0 {
        String::new()
    } else {
        (numerator as f64 / denominator as f64).to_string()
    }
}

fn peak_rss_kb() -> u64 {
    std::fs::read_to_string("/proc/self/status")
        .ok()
        .and_then(|status| {
            status.lines().find_map(|line| {
                line.strip_prefix("VmHWM:")?
                    .split_whitespace()
                    .next()?
                    .parse::<u64>()
                    .ok()
            })
        })
        .unwrap_or(0)
}

fn infer_update_type(add_rrs: &[Record], del_rrs: &[Record]) -> String {
    let mut parts = vec![];
    if !add_rrs.is_empty() {
        parts.push(format!(
            "ADD:{}",
            add_rrs
                .iter()
                .map(|rr| format!("{:?}", rr.rtype()))
                .collect::<Vec<_>>()
                .join("+")
        ));
    }
    if !del_rrs.is_empty() {
        parts.push(format!(
            "DEL:{}",
            del_rrs
                .iter()
                .map(|rr| format!("{:?}", rr.rtype()))
                .collect::<Vec<_>>()
                .join("+")
        ));
    }
    if parts.is_empty() {
        "NONE".to_string()
    } else {
        parts.join("|")
    }
}

fn apply_update_to_canonical(
    ns2zones: &mut PureNSMap,
    nameserver: &str,
    zone_file: &str,
    add_rrs: &[Record],
    del_rrs: &[Record],
) {
    let wanted = Path::new(zone_file).file_name();
    let (_, _, records) = ns2zones
        .get_mut(nameserver)
        .and_then(|zones| {
            zones.iter_mut().find(|(path, _, _)| {
                Path::new(path).file_name() == wanted
            })
        })
        .unwrap_or_else(|| panic!("canonical zone file not found: {zone_file}"));
    for deleted in del_rrs {
        if let Some(index) = records.iter().position(|record| {
            record.domain() == deleted.domain()
                && record.rtype() == deleted.rtype()
                && record.rdata() == deleted.rdata()
        }) {
            records.remove(index);
        }
    }
    records.extend(add_rrs.iter().cloned());
}

pub fn read_updates(fpath: &str) -> HashMap<String, UpdateSpec> {
    let mut rdr = csv::Reader::from_path(fpath).unwrap();
    let mut specs: HashMap<String, UpdateSpec> = HashMap::new();
    for result in rdr.records() {
        let record = result.unwrap();
        let zone = record.get(0).unwrap().to_string();
        let file_name = record.get(1).unwrap().to_string();
        let (op_idx, domain_idx, rtype_idx, rdata_idx) = if record.len() >= 7 {
            (3, 4, 5, 6)
        } else {
            (2, 3, 4, 5)
        };
        let op = record.get(op_idx).unwrap();
        let domain = crate::utils::Utils::string_to_domain(record.get(domain_idx).unwrap(), true);
        let rtype = record.get(rtype_idx).unwrap().to_string();
        let rdata = record.get(rdata_idx).unwrap().to_string();
        let rr = Record::new(domain, rtype, rdata);
        let spec = specs.entry(zone).or_insert_with(|| UpdateSpec {
            file_name: Path::new(&file_name)
                .file_name()
                .unwrap()
                .to_string_lossy()
                .to_string(),
            add_rrs: vec![],
            del_rrs: vec![],
        });
        match op {
            "ADD" => spec.add_rrs.push(rr),
            "DEL" | "DELETE" => spec.del_rrs.push(rr),
            _ => panic!("unsupported update op: {}", op),
        }
    }
    specs
}

fn read_zonefiles(zonefiles: Vec<ZoneFile>) -> Result<PureNSMap, ()> {
    let mut ns2zones: PureNSMap = HashMap::new();
    for (ns, (fpath, domain, records)) in zonefiles
        .into_par_iter()
        .filter_map(|(fpath, ns, mut domain)| {
            let records = parse(&fpath, &mut domain).unwrap_or_default();
            if records.is_empty() {
                return None;
            }
            Some((ns, (fpath, domain, records)))
        })
        .collect::<Vec<_>>()
    {
        if ns2zones.contains_key(&ns) {
            ns2zones
                .get_mut(&ns)
                .unwrap()
                .push((fpath, domain, records));
        } else {
            ns2zones.insert(ns, vec![(fpath, domain, records)]);
        }
    }
    for (_, zones) in ns2zones.iter_mut() {
        zones.sort_by(|a, b| b.1.len().cmp(&a.1.len()));
    }
    Ok(ns2zones)
}

fn get_duration(start: DateTime<Utc>) -> f64 {
    Utc::now()
        .signed_duration_since(start)
        .num_microseconds()
        .unwrap() as f64
        / 1000.0
}

#[cfg(test)]
mod tests {
    use super::*;

    fn test_config() -> Config {
        test_config_with_encoding(LabelEncodingMode::Shared)
    }

    fn test_config_with_encoding(label_encoding: LabelEncodingMode) -> Config {
        Config {
            max_query_depth: 10,
            min_label_bits: 4,
            min_label_num: 5,
            redundant_bits: 1,
            redundant_labels: 1,
            label_encoding,
            label_bit_policy: LabelBitPolicy::Reserved,
            label_cube_cache: true,
            bdd_apply_cache_capacity: 1_000_000,
            bdd_profile: false,
            bdd_threads: 1,
            rayon_threads: 1,
            lec_build_mode: LecBuildMode::Serial,
            bdd_cache: true,
        }
    }

    #[test]
    fn test_read_zonefiles() {
        let meta_path = "test_files/zonefile_rank/metadata.json";
        let (_, zonefiles) = utils::MetaParser::parse_metadata(meta_path);
        let ns2zones = read_zonefiles(zonefiles).unwrap();
        for (i, (ns, zones)) in ns2zones.iter().enumerate() {
            println!("NS{}: {}", i + 1, ns);
            println!("---------------------------------");
            for (j, (fpath, origin, records)) in zones.into_iter().enumerate() {
                println!("Zone{}:", j + 1);
                println!("fpath: {}", fpath);
                println!("origin: {:?}", origin);
                println!("records: {:?}", records);
                println!("---------------------------------");
            }
            println!()
        }
    }

    #[test]
    fn test_construction() {
        let meta_path = "test_files/bankcardExample/zone_files/metadata.json";
        let (_, zonefiles) = utils::MetaParser::parse_metadata(meta_path);
        let ns2zones = read_zonefiles(zonefiles).unwrap();
        let config = Config {
            max_query_depth: 10,
            min_label_bits: 4,
            min_label_num: 5,
            redundant_bits: 1,
            redundant_labels: 1,
            label_encoding: LabelEncodingMode::Shared,
            label_bit_policy: LabelBitPolicy::Reserved,
            label_cube_cache: true,
            bdd_apply_cache_capacity: 1_000_000,
            bdd_profile: false,
            bdd_threads: 1,
            rayon_threads: 1,
            lec_build_mode: LecBuildMode::Serial,
            bdd_cache: true,
        };
        let _ = LECManager::new(ns2zones, config);
    }

    #[test]
    fn aggregation_stats_group_rdata_but_not_distinct_owners() {
        let nameserver = "ns1.example.com.".to_string();
        let zone_file = "example.com.zone".to_string();
        let origin = vec!["com".to_string(), "example".to_string()];
        let records = vec![
            Record::new(
                vec!["com".to_string(), "example".to_string(), "www".to_string()],
                "A".to_string(),
                "192.0.2.1".to_string(),
            ),
            Record::new(
                vec!["com".to_string(), "example".to_string(), "www".to_string()],
                "A".to_string(),
                "192.0.2.2".to_string(),
            ),
            Record::new(
                vec!["com".to_string(), "example".to_string(), "mail".to_string()],
                "A".to_string(),
                "192.0.2.3".to_string(),
            ),
        ];
        let input = HashMap::from([(
            nameserver.clone(),
            vec![(zone_file.clone(), origin, records)],
        )]);
        let accepted = HashMap::from([((nameserver, zone_file), 3)]);

        let manager = LECManager::new(input, test_config());
        let stats = manager.zone_aggregation_stats(&accepted);

        assert_eq!(stats.len(), 1);
        assert_eq!(stats[0].accepted_input_rr_count, 3);
        assert_eq!(stats[0].grouped_rule_count, 2);
        assert_eq!(stats[0].record_lec_count, 2);
        assert_eq!(stats[0].synthetic_refuse_count, 1);
        assert_eq!(stats[0].total_lec_count, 3);
        assert_eq!(manager.num_record_lecs(), 2);
        assert_eq!(manager.num_lec(), 3);
    }

    #[test]
    fn aggregation_stats_expand_cname_and_dname_rewrite_rules() {
        for (rtype, owner, target) in [
            ("CNAME", "alias", "target.example.com."),
            ("DNAME", "branch", "target.example.net."),
        ] {
            let nameserver = "ns1.example.com.".to_string();
            let zone_file = format!("{rtype}.zone");
            let origin = vec!["com".to_string(), "example".to_string()];
            let records = vec![Record::new(
                vec!["com".to_string(), "example".to_string(), owner.to_string()],
                rtype.to_string(),
                target.to_string(),
            )];
            let input = HashMap::from([(
                nameserver.clone(),
                vec![(zone_file.clone(), origin, records)],
            )]);
            let accepted = HashMap::from([((nameserver, zone_file), 1)]);

            let manager = LECManager::new(input, test_config());
            let stats = manager.zone_aggregation_stats(&accepted);

            assert_eq!(stats[0].accepted_input_rr_count, 1);
            assert_eq!(stats[0].grouped_rule_count, 2);
            assert_eq!(stats[0].record_lec_count, 2);
            assert_eq!(stats[0].synthetic_refuse_count, 1);
            assert_eq!(stats[0].total_lec_count, 3);
        }
    }

    #[test]
    fn aggregation_stats_exclude_shadowed_empty_bdds() {
        let nameserver = "ns1.example.com.".to_string();
        let zone_file = "shadowed.zone".to_string();
        let origin = vec!["com".to_string(), "example".to_string()];
        let owner = vec!["com".to_string(), "example".to_string(), "child".to_string()];
        let records = vec![
            Record::new(owner.clone(), "NS".to_string(), "ns.child.example.com.".to_string()),
            Record::new(owner, "A".to_string(), "192.0.2.1".to_string()),
        ];
        let input = HashMap::from([(
            nameserver.clone(),
            vec![(zone_file.clone(), origin, records)],
        )]);
        let accepted = HashMap::from([((nameserver, zone_file), 2)]);

        let manager = LECManager::new(input, test_config());
        let stats = manager.zone_aggregation_stats(&accepted);

        assert_eq!(stats[0].accepted_input_rr_count, 2);
        assert_eq!(stats[0].grouped_rule_count, 2);
        assert_eq!(stats[0].record_lec_count, 1);
        assert_eq!(stats[0].synthetic_refuse_count, 1);
        assert_eq!(stats[0].total_lec_count, 2);
    }

    #[test]
    fn per_layer_encoding_uses_independent_bit_widths() {
        let nameserver = "ns1.example.com.".to_string();
        let zone_file = "per-layer.zone".to_string();
        let origin = vec!["com".to_string(), "example".to_string()];
        let records = (0..20)
            .map(|index| {
                Record::new(
                    vec![
                        "com".to_string(),
                        "example".to_string(),
                        format!("host{index}"),
                    ],
                    "A".to_string(),
                    format!("192.0.2.{index}"),
                )
            })
            .collect::<Vec<_>>();
        let input = HashMap::from([(nameserver, vec![(zone_file, origin, records)])]);

        let manager = LECManager::new(
            input,
            test_config_with_encoding(LabelEncodingMode::PerLayer),
        );
        let stats = manager.construction_stats();

        assert_eq!(stats.unique_label_table_count, stats.label_level_count);
        assert!(stats.label_bits_min < stats.label_bits_max);
        assert_eq!(
            stats.total_bits,
            stats.label_bits_by_level.iter().sum::<usize>() + stats.rtype_bits
        );
        assert_eq!(stats.bdd_variable_count, stats.total_bits);
        assert_eq!(stats.shared_label_tail_start, None);
    }

    #[test]
    fn per_layer_dname_uses_a_compatible_shared_tail() {
        let nameserver = "ns1.example.com.".to_string();
        let zone_file = "dname-per-layer.zone".to_string();
        let origin = vec!["com".to_string(), "example".to_string()];
        let records = vec![
            Record::new(
                vec!["com".to_string(), "example".to_string(), "branch".to_string()],
                "DNAME".to_string(),
                "target.net.".to_string(),
            ),
            Record::new(
                vec!["com".to_string(), "example".to_string(), "www".to_string()],
                "A".to_string(),
                "192.0.2.1".to_string(),
            ),
        ];
        let input = HashMap::from([(
            nameserver.clone(),
            vec![(zone_file, origin, records)],
        )]);
        let shared = LECManager::new(input.clone(), test_config());
        let per_layer = LECManager::new(
            input,
            test_config_with_encoding(LabelEncodingMode::PerLayer),
        );

        let stats = per_layer.construction_stats();
        assert_eq!(stats.shared_label_tail_start, Some(2));
        assert_eq!(stats.unique_label_table_count, 3);
        assert!(stats.label_bits_by_level[2..]
            .windows(2)
            .all(|bits| bits[0] == bits[1]));
        assert_eq!(shared.num_lec(), per_layer.num_lec());

        let shared_traces = shared.symbolic_exec_par(None, std::slice::from_ref(&nameserver));
        let per_layer_traces =
            per_layer.symbolic_exec_par(None, std::slice::from_ref(&nameserver));
        assert_eq!(shared_traces.get_num_logs(), per_layer_traces.get_num_logs());
        assert_eq!(shared_traces.get_num_traces(), per_layer_traces.get_num_traces());
        let mut shared_errors = shared.property_checking(&shared_traces, &HashSet::new());
        let mut per_layer_errors = per_layer.property_checking(&per_layer_traces, &HashSet::new());
        shared_errors.sort();
        per_layer_errors.sort();
        assert_eq!(shared_errors, per_layer_errors);
    }

    fn optimization_test_input() -> (PureNSMap, Vec<String>) {
        let nameserver = "ns1.example.com.".to_string();
        let origin = vec!["com".to_string(), "example".to_string()];
        let records = vec![
            Record::new(
                vec!["com".to_string(), "example".to_string(), "www".to_string()],
                "A".to_string(),
                "192.0.2.1".to_string(),
            ),
            Record::new(
                vec!["com".to_string(), "example".to_string(), "mail".to_string()],
                "A".to_string(),
                "192.0.2.2".to_string(),
            ),
            Record::new(
                vec!["com".to_string(), "example".to_string(), "alias".to_string()],
                "CNAME".to_string(),
                "www.example.com.".to_string(),
            ),
        ];
        (
            HashMap::from([(
                nameserver.clone(),
                vec![("example.zone".to_string(), origin, records)],
            )]),
            vec![nameserver],
        )
    }

    #[test]
    fn compact_bits_preserve_initial_verification_semantics() {
        let (input, top_ns) = optimization_test_input();
        let mut reserved_config = test_config_with_encoding(LabelEncodingMode::PerLayer);
        reserved_config.bdd_cache = false;
        let mut compact_config = reserved_config.clone();
        compact_config.label_bit_policy = LabelBitPolicy::Compact;

        let reserved = LECManager::new(input.clone(), reserved_config);
        let compact = LECManager::new(input, compact_config);
        let reserved_traces = reserved.symbolic_exec_par(None, &top_ns);
        let compact_traces = compact.symbolic_exec_par(None, &top_ns);
        let jobs = HashSet::new();

        assert!(compact.construction_stats().total_bits < reserved.construction_stats().total_bits);
        assert_eq!(compact.num_lec(), reserved.num_lec());
        assert_eq!(compact.num_records(), reserved.num_records());
        assert_eq!(compact.lec_semantic_hash(), reserved.lec_semantic_hash());
        assert_eq!(
            compact.trace_semantic_hash(&compact_traces),
            reserved.trace_semantic_hash(&reserved_traces)
        );
        assert_eq!(compact_traces.get_num_traces(), reserved_traces.get_num_traces());
        assert_eq!(compact_traces.get_num_logs(), reserved_traces.get_num_logs());
        assert_eq!(
            compact.property_checking(&compact_traces, &jobs),
            reserved.property_checking(&reserved_traces, &jobs)
        );
    }

    #[test]
    fn label_cube_cache_preserves_semantics_and_records_hits() {
        let (input, top_ns) = optimization_test_input();
        let mut uncached_config = test_config_with_encoding(LabelEncodingMode::PerLayer);
        uncached_config.bdd_cache = false;
        uncached_config.label_cube_cache = false;
        let mut cached_config = uncached_config.clone();
        cached_config.label_cube_cache = true;

        let uncached = LECManager::new(input.clone(), uncached_config);
        let cached = LECManager::new(input, cached_config);
        let uncached_traces = uncached.symbolic_exec_par(None, &top_ns);
        let cached_traces = cached.symbolic_exec_par(None, &top_ns);

        assert_eq!(cached.num_lec(), uncached.num_lec());
        assert_eq!(cached.lec_semantic_hash(), uncached.lec_semantic_hash());
        assert_eq!(
            cached.trace_semantic_hash(&cached_traces),
            uncached.trace_semantic_hash(&uncached_traces)
        );
        assert_eq!(cached_traces.get_num_traces(), uncached_traces.get_num_traces());
        assert_eq!(cached_traces.get_num_logs(), uncached_traces.get_num_logs());
        assert!(cached.construction_stats().label_cube_cache_hits > 0);
        assert!(cached.construction_stats().label_cube_cache_misses > 0);
    }

    #[test]
    fn full_only_drops_record_hits_without_changing_verification_semantics() {
        let (input, top_ns) = optimization_test_input();
        let config = test_config_with_encoding(LabelEncodingMode::PerLayer);
        let incremental = LECManager::new(input.clone(), config.clone());
        let full_only = LECManager::new_full_only(input, config);

        assert_eq!(
            incremental.num_retained_record_hits(),
            incremental.num_records()
        );
        assert_eq!(incremental.construction_stats().retained_record_hit_count,
                   incremental.num_records());
        assert_eq!(full_only.num_retained_record_hits(), 0);
        assert_eq!(full_only.construction_stats().retained_record_hit_count, 0);
        assert_eq!(full_only.num_lec(), incremental.num_lec());
        assert_eq!(full_only.lec_semantic_hash(), incremental.lec_semantic_hash());

        let incremental_traces = incremental.symbolic_exec_par(None, &top_ns);
        let full_only_traces = full_only.symbolic_exec_par(None, &top_ns);
        assert_eq!(
            full_only.trace_semantic_hash(&full_only_traces),
            incremental.trace_semantic_hash(&incremental_traces)
        );
        assert_eq!(
            full_only.property_checking(&full_only_traces, &HashSet::new()),
            incremental.property_checking(&incremental_traces, &HashSet::new())
        );
    }

    #[test]
    fn encoding_update_validation_detects_capacity_depth_and_dname_rebuilds() {
        let nameserver = "ns1.example.com.".to_string();
        let origin = vec!["com".to_string(), "example".to_string()];
        let input = HashMap::from([(
            nameserver,
            vec![(
                "example.zone".to_string(),
                origin,
                vec![Record::new(
                    vec!["com".to_string(), "example".to_string(), "www".to_string()],
                    "A".to_string(),
                    "192.0.2.1".to_string(),
                )],
            )],
        )]);
        let mut config = test_config_with_encoding(LabelEncodingMode::PerLayer);
        config.label_bit_policy = LabelBitPolicy::Compact;
        let manager = LECManager::new(input, config);

        let capacity_update = vec![
            Record::new(
                vec!["com".to_string(), "example".to_string(), "one".to_string()],
                "A".to_string(),
                "192.0.2.2".to_string(),
            ),
            Record::new(
                vec!["com".to_string(), "example".to_string(), "two".to_string()],
                "A".to_string(),
                "192.0.2.3".to_string(),
            ),
        ];
        assert!(manager
            .validate_encoding_update(&capacity_update)
            .unwrap_err()
            .contains("capacity"));

        let too_deep = vec![Record::new(
            vec!["com", "example", "a", "b", "c", "d", "e"]
                .into_iter()
                .map(str::to_string)
                .collect(),
            "A".to_string(),
            "192.0.2.4".to_string(),
        )];
        assert!(manager
            .validate_encoding_update(&too_deep)
            .unwrap_err()
            .contains("depth"));

        let incompatible_dname = vec![Record::new(
            vec!["com".to_string(), "example".to_string(), "branch".to_string()],
            "DNAME".to_string(),
            "target.net.".to_string(),
        )];
        assert!(manager
            .validate_encoding_update(&incompatible_dname)
            .unwrap_err()
            .contains("DNAME"));
    }
}
