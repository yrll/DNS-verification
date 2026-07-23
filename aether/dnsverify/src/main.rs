use clap::{Parser, Subcommand};
use dnsv::{read_updates, run, Config, LabelBitPolicy, RunOptions};
use dnsv::utils::MetaParser;
use env_logger::Builder;
use std::{collections::HashSet, io::BufRead};

fn main() {
    let mut builder = Builder::new();
    builder
        .filter_level(log::LevelFilter::Debug)
        .parse_default_env();
    builder.init();

    let args: Cli = Cli::parse();

    match args.input {
        Input::MetaData {
            domain: _,
            metadata: _,
        } => subcommand_m(args),
        Input::Csv { csv: _ } => subcommand_c(args),
    };
}

fn get_jobs(jobs: Option<String>) -> HashSet<String> {
    match jobs {
        Some(jobs) => {
            let file = std::fs::File::open(jobs).unwrap();
            let reader = std::io::BufReader::new(file);
            reader
                .lines()
                .map(|line| line.unwrap().trim().to_string())
                .filter(|line| !line.is_empty())
                .collect::<HashSet<String>>()
        }
        None => HashSet::from_iter(vec![
            "hops".to_string(),
            "rewrites".to_string(),
            "too long".to_string(),
            "zone loop".to_string(),
            "delegation consistency".to_string(),
            "lame delegation".to_string(),
            "rewrite blackholing".to_string(),
        ]),
    }
}

fn subcommand_m(args: Cli) {
    println!("{:?}", args);
}

fn subcommand_c(args: Cli) {
    assert!(args.bdd_threads > 0, "--bdd-threads must be at least 1");
    assert!(args.rayon_threads > 0, "--rayon-threads must be at least 1");
    assert!(args.worker_stack_mb > 0, "--worker-stack-mb must be at least 1");
    let worker_stack_bytes = args.worker_stack_mb * 1024 * 1024;
    std::env::set_var("RUST_MIN_STACK", worker_stack_bytes.to_string());
    rayon::ThreadPoolBuilder::new()
        .num_threads(args.rayon_threads)
        .stack_size(worker_stack_bytes)
        .build_global()
        .expect("failed to configure the global Rayon thread pool");
    let jobs = get_jobs(args.jobs);
    let output = args.output.unwrap_or("output.csv".to_string());
    let trace = args.trace.unwrap_or("traces".to_string());
    let updates = args.updates.as_ref().map(|path| read_updates(path));
    if args.no_random_update && updates.is_none() && !args.full_only {
        panic!("--no-random-update requires --updates");
    }
    if args.full_only && updates.is_some() {
        panic!("--full-only cannot be combined with --updates");
    }
    let label_bit_policy = args
        .label_bit_policy
        .parse::<LabelBitPolicy>()
        .unwrap()
        .resolve(args.full_only);
    let options = RunOptions {
        config: Config {
            max_query_depth: args.max_query_depth,
            min_label_bits: args.min_label_bits,
            min_label_num: args.min_label_num,
            redundant_bits: 1,
            redundant_labels: 1,
            label_encoding: args.label_encoding.parse().unwrap(),
            label_bit_policy,
            label_cube_cache: args.label_cube_cache,
            bdd_apply_cache_capacity: args.bdd_apply_cache_capacity,
            bdd_profile: args.bdd_profile,
            bdd_threads: args.bdd_threads,
            rayon_threads: args.rayon_threads,
            lec_build_mode: args.lec_build_mode.parse().unwrap(),
            bdd_cache: args.bdd_cache,
        },
        no_random_update: args.no_random_update,
        full_only: args.full_only,
        repeat: args.repeat,
        dump_traces: args.dump_traces,
    };
    let csv_file = match args.input {
        Input::Csv { csv } => csv,
        _ => unreachable!(),
    };

    let mut rdr = csv::Reader::from_path(csv_file).unwrap();
    let mut out = csv::Writer::from_path(output).unwrap();
    let mut zone_stats_out = args.zone_stats.map(|path| {
        let mut writer = csv::Writer::from_path(path).unwrap();
        writer
            .write_record([
                "zone",
                "nameserver",
                "zone_file",
                "origin",
                "accepted_input_rr_count",
                "grouped_rule_count",
                "record_lec_count",
                "synthetic_refuse_count",
                "total_lec_count",
                "record_lec_ratio",
                "total_table_ratio",
            ])
            .unwrap();
        writer
    });
    out.write_record([
        "zone",
        "num_lec",
        "io_time (ms)",
        "construction_time (ms)",
        "symbolic_time (ms)",
        "property_checking_time (ms)",
        "re_construction_time (ms)",
        "re_symbolic_time (ms)",
        "re_property_checking_time (ms)",
        "properties",
        "initial_property_pass",
        "initial_errors",
        "incremental_property_pass",
        "incremental_errors",
        "rr_count",
        "zone_file_count",
        "trace_count",
        "log_count",
        "affected_trace_count",
        "update_add_count",
        "update_del_count",
        "update_type",
        "encoding_rebuild_required",
        "incremental_fallback_full_rebuild",
        "fallback_reason",
        "max_query_depth",
        "min_label_num",
        "min_label_bits",
        "label_encoding",
        "effective_label_bit_policy",
        "label_cube_cache",
        "bdd_apply_cache_capacity",
        "bdd_profile",
        "bdd_threads",
        "rayon_threads",
        "lec_build_mode",
        "bdd_cache",
        "construction_preprocess_ms",
        "construction_bdd_setup_ms",
        "construction_lec_build_ms",
        "label_level_count",
        "unique_label_table_count",
        "label_value_count_min",
        "label_value_count_max",
        "label_bits_min",
        "label_bits_max",
        "label_bits_by_level",
        "label_values_by_level",
        "shared_label_tail_start",
        "name_bits",
        "rtype_count",
        "rtype_bits",
        "total_bits",
        "compact_total_bits",
        "bdd_variable_count",
        "bdd_node_count",
        "retained_record_hit_count",
        "bdd_cache_hits",
        "bdd_cache_misses",
        "label_cube_cache_hits",
        "label_cube_cache_misses",
        "query_encode_calls",
        "lec_query_encoding_ms",
        "lec_record_partition_ms",
        "lec_zone_ns_union_ms",
        "peak_rss_kb",
        "worker_stack_mb",
        "full_only",
        "accepted_input_rr_count",
        "grouped_rule_count",
        "record_lec_count",
        "synthetic_refuse_count",
        "total_lec_count",
        "lec_semantic_hash",
        "trace_semantic_hash",
    ])
    .unwrap();

    let mut idx = 0;
    let path = std::path::Path::new(&trace);
    if !path.exists() {
        std::fs::create_dir_all(path).unwrap();
    }

    for (i, result) in rdr.records().enumerate().map(|(i, r)| (i + 1, r)) {
        let record = result.unwrap();
        let zone = record.get(0).unwrap();
        let meta_path = record.get(1).unwrap();

        let (top_ns, zonefiles) = MetaParser::parse_metadata(meta_path);
        let update_spec = updates.as_ref().and_then(|updates| updates.get(zone).cloned());

        let sub_dir_path = path.join(format!("trace_{:03}", idx));
        std::fs::create_dir_all(&sub_dir_path).unwrap();
        let trace_name = zone.replace(['/', '\\'], "__");
        let trace_file = sub_dir_path.join(format!("{}.log", trace_name));
        let trace_file = trace_file.to_str().unwrap().to_string();
        let mut trace_fp = std::fs::File::create(&trace_file).unwrap();
        for _ in 0..options.repeat {
            run(
                top_ns.clone(),
                zonefiles.clone(),
                zone,
                &jobs,
                &mut out,
                zone_stats_out.as_mut(),
                &mut trace_fp,
                update_spec.clone(),
                &options,
            );
        }

        if i % 1000 == 0 {
            idx += 1;
            print!("Processed {} zones\r", i);
        }
    }
}

#[derive(Parser, Debug)]
#[command(author="Yao", version, about, long_about = None)]
struct Cli {
    #[command(subcommand)]
    input: Input,
    /// A json file, to store the properties needed to be verified
    #[arg(short, long)]
    jobs: Option<String>,
    /// A csv file, to store the performance result
    #[arg(short, long)]
    output: Option<String>,
    /// A log file / dir, to store the log(s)
    #[arg(short, long)]
    trace: Option<String>,
    /// A CSV file of deterministic updates. Header: zone,file,op,domain,type,rdata
    #[arg(short, long)]
    updates: Option<String>,
    /// Maximum symbolic query depth.
    #[arg(long, default_value_t = 10)]
    max_query_depth: usize,
    /// Minimum number of labels in bounded domain encoding.
    #[arg(long, default_value_t = 5)]
    min_label_num: usize,
    /// Minimum bits per label in bounded domain encoding.
    #[arg(long, default_value_t = 4)]
    min_label_bits: usize,
    /// Label dictionary layout: shared across all levels or DNAME-compatible per-level tables.
    #[arg(long, default_value = "shared", value_parser = ["shared", "per-layer"])]
    label_encoding: String,
    /// Label bit allocation: automatic, capacity-reserved, or compact.
    #[arg(long, default_value = "auto", value_parser = ["auto", "reserved", "compact"])]
    label_bit_policy: String,
    /// Cache equality BDDs for individual labels.
    #[arg(long, default_value_t = true, action = clap::ArgAction::Set)]
    label_cube_cache: bool,
    /// OxiDD apply-cache capacity.
    #[arg(long, default_value_t = 1_000_000)]
    bdd_apply_cache_capacity: usize,
    /// Enable detailed BDD construction profiling.
    #[arg(long)]
    bdd_profile: bool,
    /// Repeat each CSV row this many times.
    #[arg(long, default_value_t = 1)]
    repeat: usize,
    /// Disable random updates; requires --updates.
    #[arg(long)]
    no_random_update: bool,
    /// Run initial verification only and skip all update processing.
    #[arg(long)]
    full_only: bool,
    /// Optional CSV path for per-zone LEC aggregation statistics.
    #[arg(long)]
    zone_stats: Option<String>,
    /// Number of worker threads used internally by OxiDD.
    #[arg(long, default_value_t = 1)]
    bdd_threads: usize,
    /// Number of Rayon workers used for nameserver-level LEC construction.
    #[arg(long, default_value_t = 1)]
    rayon_threads: usize,
    /// LEC construction strategy: serial or parallel across nameservers.
    #[arg(long, default_value = "serial", value_parser = ["serial", "parallel"])]
    lec_build_mode: String,
    /// Enable the construction-time query BDD cache.
    #[arg(long, default_value_t = true, action = clap::ArgAction::Set)]
    bdd_cache: bool,
    /// Stack size for Rayon and OxiDD workers; large BDDs use recursive apply operations.
    #[arg(long, default_value_t = 16)]
    worker_stack_mb: usize,
    /// Write detailed LEC and symbolic trace stores.
    #[arg(long, default_value_t = true, action = clap::ArgAction::Set)]
    dump_traces: bool,
}

#[derive(Subcommand, Debug)]
#[group(required = true, multiple = false)]
enum Input {
    /// Input a domain (zone name) and a metadata file
    #[command(name = "m")]
    MetaData {
        /// A domain name
        domain: String,
        /// A metadata file
        metadata: String,
    },
    /// A csv file, to store all metadata. Header: Domain, Metadata Path
    #[command(name = "c")]
    Csv {
        /// A csv file
        csv: String,
    },
}

