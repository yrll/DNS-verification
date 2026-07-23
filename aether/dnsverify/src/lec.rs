mod action;
mod label_info;
mod name_server_bdd;
mod query;
mod record_bdd;
mod trace_log;
mod zonefile_bdd;

use crate::record::{Record, RecordType};
use crate::utils::Utils;
use crate::{Config, Domain, FPath, LabelBitPolicy, LabelEncodingMode, LecBuildMode, PureNSMap, NS};
use action::{ActionCache, ActionType};
use label_info::LabelInfo;
use name_server_bdd::NameServerBDD;
use oxidd::{
    bdd::{BDDFunction, BDDManagerRef},
    BooleanFunction, Function, FunctionSubst, Manager, ManagerRef, Subst,
};
use oxidd_dump::dddmp;
use query::Query;
use rand::distributions::WeightedIndex;
use rand::prelude::*;
use rayon::prelude::*;
use record_bdd::RecordBDD;
use sha2::{Digest, Sha256};
use std::collections::{HashMap, HashSet};
use std::io::{Cursor, Write};
use std::sync::{
    atomic::{AtomicU64, Ordering},
    Arc, RwLock,
};
use std::time::Instant;
use std::vec;
use strum::{EnumCount, IntoEnumIterator};
use trace_log::TraceLogManager;
use zonefile_bdd::ZoneFileBDD;

const WILDCARD: &str = "*"; // 通配符
const ALPHA: &str = "\u{03B1}"; // 1. wildcard + empty，2. 该层未出现过的label
const MAX_QUERY_DEPTH: usize = 10;

type BDDResult = oxidd::util::AllocResult<BDDFunction>;
type Records = HashMap<(Domain, RecordType, usize), HashSet<String>>;
type NSMap = HashMap<NS, Vec<(FPath, Domain, Records)>>;

#[derive(Debug, Clone, PartialEq)]
pub struct ZoneAggregationStats {
    pub nameserver: String,
    pub zone_file: String,
    pub origin: String,
    pub accepted_input_rr_count: usize,
    pub grouped_rule_count: usize,
    pub record_lec_count: usize,
    pub synthetic_refuse_count: usize,
    pub total_lec_count: usize,
}
type QueryBDDKey = (Domain, RecordType, usize);

struct ProfileTimer<'a> {
    start: Option<Instant>,
    sink: &'a AtomicU64,
}

impl<'a> ProfileTimer<'a> {
    fn new(enabled: bool, sink: &'a AtomicU64) -> Self {
        Self {
            start: enabled.then(Instant::now),
            sink,
        }
    }
}

impl Drop for ProfileTimer<'_> {
    fn drop(&mut self) {
        if let Some(start) = self.start {
            self.sink.fetch_add(
                start.elapsed().as_nanos().min(u64::MAX as u128) as u64,
                Ordering::Relaxed,
            );
        }
    }
}

#[derive(Clone, Debug, Default)]
pub struct ConstructionStats {
    pub preprocess_ms: f64,
    pub bdd_setup_ms: f64,
    pub lec_build_ms: f64,
    pub label_level_count: usize,
    pub unique_label_table_count: usize,
    pub label_value_count_min: usize,
    pub label_value_count_max: usize,
    pub label_bits_min: usize,
    pub label_bits_max: usize,
    pub label_bits_by_level: Vec<usize>,
    pub label_values_by_level: Vec<usize>,
    pub shared_label_tail_start: Option<usize>,
    pub name_bits: usize,
    pub rtype_count: usize,
    pub rtype_bits: usize,
    pub total_bits: usize,
    pub compact_total_bits: usize,
    pub bdd_variable_count: usize,
    pub bdd_node_count: usize,
    pub retained_record_hit_count: usize,
    pub cache_hits: u64,
    pub cache_misses: u64,
    pub label_cube_cache_hits: u64,
    pub label_cube_cache_misses: u64,
    pub query_encode_calls: u64,
    pub lec_query_encoding_ms: f64,
    pub lec_record_partition_ms: f64,
    pub lec_zone_ns_union_ms: f64,
}
// num_bit, label -> value

#[allow(dead_code)]
pub struct LECManager {
    // BDD fields
    manager_ref: BDDManagerRef,
    vars: Vec<BDDFunction>,
    bdd_t: BDDFunction,
    bdd_f: BDDFunction,

    // 配置信息
    config: Config,
    name_bits: usize,
    rtype_bits: usize,
    total_bits: usize,
    retain_record_hits: bool,

    // 一些加速的cache
    wildcard_bdds: Vec<BDDFunction>,
    empty_bdds: Vec<BDDFunction>,
    wildcard_empty_bdds: Vec<BDDFunction>,
    rtypes: HashMap<RecordType, BDDFunction>,
    query_bdd_cache: RwLock<HashMap<QueryBDDKey, BDDFunction>>,
    label_cube_cache: Vec<RwLock<HashMap<usize, BDDFunction>>>,
    cache_hits: AtomicU64,
    cache_misses: AtomicU64,
    label_cube_cache_hits: AtomicU64,
    label_cube_cache_misses: AtomicU64,
    query_encode_calls: AtomicU64,
    profile_query_encoding_ns: AtomicU64,
    profile_record_partition_ns: AtomicU64,
    profile_zone_ns_union_ns: AtomicU64,

    // 各层label编码表
    label_infos: Vec<LabelInfo>,

    // data
    ns_map: HashMap<String, NameServerBDD>,
    construction_stats: ConstructionStats,
}

// public methods
#[allow(dead_code)]
impl LECManager {
    pub fn new(ns2zones: PureNSMap, config: Config) -> LECManager {
        Self::new_with_record_hits(ns2zones, config, true)
    }

    pub fn new_full_only(ns2zones: PureNSMap, config: Config) -> LECManager {
        Self::new_with_record_hits(ns2zones, config, false)
    }

    fn new_with_record_hits(
        ns2zones: PureNSMap,
        config: Config,
        retain_record_hits: bool,
    ) -> LECManager {
        if config.max_query_depth > MAX_QUERY_DEPTH {
            panic!(
                "max_query_depth must be less than or equal to {}",
                MAX_QUERY_DEPTH
            );
        }
        // let (ns2czones, label_infos) = Self::preprocess_zonefiles(ns2zones, &config);
        let preprocess_start = Instant::now();
        let (ns2czones, label_infos, shared_label_tail_start) =
            Self::preprocess_zonefiles_par(ns2zones, &config);
        let preprocess_ms = preprocess_start.elapsed().as_secs_f64() * 1000.0;
        let name_bits = label_infos
            .iter()
            .map(|info| info.get_num_bit())
            .sum::<usize>();
        let label_level_count = label_infos.len();
        let label_bits_min = label_infos
            .iter()
            .map(|info| info.get_num_bit())
            .min()
            .unwrap_or(0);
        let label_bits_max = label_infos
            .iter()
            .map(|info| info.get_num_bit())
            .max()
            .unwrap_or(0);
        let label_value_counts = label_infos
            .iter()
            .map(|info| info.words_table().read().unwrap().len())
            .collect::<Vec<_>>();
        let label_value_count_min = label_value_counts.iter().copied().min().unwrap_or(0);
        let label_value_count_max = label_value_counts.iter().copied().max().unwrap_or(0);
        let label_bits_by_level = label_infos
            .iter()
            .map(|info| info.get_num_bit())
            .collect::<Vec<_>>();
        let unique_label_table_count = label_infos
            .iter()
            .map(|info| Arc::as_ptr(info.words_table()) as usize)
            .collect::<HashSet<_>>()
            .len();
        let rtype_count = RecordType::COUNT;
        let rtype_bits = (RecordType::COUNT as f64).log2().ceil() as usize;
        let total_bits = name_bits + rtype_bits;
        let compact_total_bits = label_value_counts
            .iter()
            .map(|count| {
                if *count <= 1 {
                    1
                } else {
                    usize::BITS as usize - (*count - 1).leading_zeros() as usize
                }
            })
            .sum::<usize>()
            + rtype_bits;
        let bdd_setup_start = Instant::now();
        let (manager_ref, vars, bdd_t, bdd_f) = Self::bdd_setup(total_bits, &config);
        let bdd_variable_count = vars.len();
        let (wildcard_bdds, empty_bdds, wildcard_empty_bdds) =
            Self::wildcard_bdd_setup(&label_infos, &vars, &bdd_t);
        let rtypes = Self::rtype_bdd_setup(name_bits, &vars, &bdd_t, &bdd_f);
        let label_cube_cache = (0..label_infos.len())
            .map(|_| RwLock::new(HashMap::new()))
            .collect();
        let bdd_setup_ms = bdd_setup_start.elapsed().as_secs_f64() * 1000.0;
        let mut lec_manager = LECManager {
            manager_ref,
            vars,
            bdd_t,
            bdd_f,

            config,
            name_bits,
            rtype_bits,
            total_bits,
            retain_record_hits,

            wildcard_bdds,
            empty_bdds,
            wildcard_empty_bdds,
            rtypes,
            query_bdd_cache: RwLock::new(HashMap::new()),
            label_cube_cache,
            cache_hits: AtomicU64::new(0),
            cache_misses: AtomicU64::new(0),
            label_cube_cache_hits: AtomicU64::new(0),
            label_cube_cache_misses: AtomicU64::new(0),
            query_encode_calls: AtomicU64::new(0),
            profile_query_encoding_ns: AtomicU64::new(0),
            profile_record_partition_ns: AtomicU64::new(0),
            profile_zone_ns_union_ns: AtomicU64::new(0),

            label_infos,

            ns_map: HashMap::new(),
            construction_stats: ConstructionStats {
                preprocess_ms,
                bdd_setup_ms,
                label_level_count,
                unique_label_table_count,
                label_value_count_min,
                label_value_count_max,
                label_bits_min,
                label_bits_max,
                label_bits_by_level,
                label_values_by_level: label_value_counts,
                shared_label_tail_start,
                name_bits,
                rtype_count,
                rtype_bits,
                total_bits,
                compact_total_bits,
                bdd_variable_count,
                ..ConstructionStats::default()
            },
        };

        let lec_build_start = Instant::now();
        match lec_manager.config.lec_build_mode {
            LecBuildMode::Serial => lec_manager.build_lec(ns2czones),
            LecBuildMode::Parallel => lec_manager.build_lec_par(ns2czones),
        }
        lec_manager.construction_stats.lec_build_ms =
            lec_build_start.elapsed().as_secs_f64() * 1000.0;
        lec_manager.construction_stats.bdd_node_count = lec_manager
            .manager_ref
            .with_manager_shared(|manager| manager.approx_num_inner_nodes());
        lec_manager.construction_stats.retained_record_hit_count =
            lec_manager.num_retained_record_hits();
        lec_manager.construction_stats.cache_hits =
            lec_manager.cache_hits.load(Ordering::Relaxed);
        lec_manager.construction_stats.cache_misses =
            lec_manager.cache_misses.load(Ordering::Relaxed);
        lec_manager.construction_stats.label_cube_cache_hits =
            lec_manager.label_cube_cache_hits.load(Ordering::Relaxed);
        lec_manager.construction_stats.label_cube_cache_misses =
            lec_manager.label_cube_cache_misses.load(Ordering::Relaxed);
        lec_manager.construction_stats.query_encode_calls =
            lec_manager.query_encode_calls.load(Ordering::Relaxed);
        lec_manager.construction_stats.lec_query_encoding_ms =
            lec_manager.profile_query_encoding_ns.load(Ordering::Relaxed) as f64 / 1_000_000.0;
        lec_manager.construction_stats.lec_record_partition_ms =
            lec_manager.profile_record_partition_ns.load(Ordering::Relaxed) as f64 / 1_000_000.0;
        lec_manager.construction_stats.lec_zone_ns_union_ms =
            lec_manager.profile_zone_ns_union_ns.load(Ordering::Relaxed) as f64 / 1_000_000.0;

        lec_manager
    }

    pub fn construction_stats(&self) -> ConstructionStats {
        self.construction_stats.clone()
    }

    pub fn num_lec(&self) -> usize {
        let mut count = 0;
        for (_, ns) in self.ns_map.iter() {
            for zone in ns.zones().values() {
                for (_, record) in zone.records() {
                    if record.bdd() != &self.bdd_f {
                        count += 1;
                    }
                }
                count += 1; // refuse
            }
        }
        count
    }

    pub fn num_record_lecs(&self) -> usize {
        self.ns_map
            .values()
            .flat_map(|ns| ns.zones().values())
            .flat_map(|zone| zone.records().values())
            .filter(|record| record.bdd() != &self.bdd_f)
            .count()
    }

    pub fn zone_aggregation_stats(
        &self,
        accepted_input_rr_counts: &HashMap<(String, String), usize>,
    ) -> Vec<ZoneAggregationStats> {
        let mut stats = self
            .ns_map
            .iter()
            .flat_map(|(nameserver, ns)| {
                ns.zones().values().map(move |zone| {
                    let grouped_rule_count = zone.records().len();
                    let record_lec_count = zone
                        .records()
                        .values()
                        .filter(|record| record.bdd() != &self.bdd_f)
                        .count();
                    let synthetic_refuse_count = 1;
                    ZoneAggregationStats {
                        nameserver: nameserver.clone(),
                        zone_file: zone.fpath().clone(),
                        origin: Utils::domain_to_string(zone.origin()),
                        accepted_input_rr_count: *accepted_input_rr_counts
                            .get(&(nameserver.clone(), zone.fpath().clone()))
                            .unwrap_or(&0),
                        grouped_rule_count,
                        record_lec_count,
                        synthetic_refuse_count,
                        total_lec_count: record_lec_count + synthetic_refuse_count,
                    }
                })
            })
            .collect::<Vec<_>>();
        stats.sort_by(|left, right| {
            (&left.nameserver, &left.zone_file).cmp(&(&right.nameserver, &right.zone_file))
        });
        stats
    }

    pub fn num_zonefiles(&self) -> usize {
        self.ns_map.values().map(|ns| ns.zones().len()).sum()
    }

    pub fn num_records(&self) -> usize {
        self.ns_map
            .values()
            .map(|ns| {
                ns.zones()
                    .values()
                    .map(|zone| zone.records().len())
                    .sum::<usize>()
            })
            .sum()
    }

    pub fn num_retained_record_hits(&self) -> usize {
        self.ns_map
            .values()
            .flat_map(|ns| ns.zones().values())
            .flat_map(|zone| zone.records().values())
            .filter(|record| record.hit().is_some())
            .count()
    }

    #[allow(deprecated)]
    pub fn symbolic_exec(&self, query: Option<Query>, nameservers: &[String]) -> TraceLogManager {
        let query = match query {
            Some(q) => q,
            _ => self.new_query(),
        };
        let mut tl_mgr = TraceLogManager::new(self.config.max_query_depth);
        let log_idx = tl_mgr.new_log(
            query.clone(),
            None,
            ActionType::Delegate,
            "".to_string(),
            None,
            None,
            None,
            None,
        );
        let mut queue = nameservers
            .iter()
            .filter_map(|name| {
                if let Some(ns) = self.ns_map.get(name) {
                    Some(ns.process_query(log_idx, query.clone(), self, &tl_mgr))
                } else {
                    None
                }
            })
            .flatten()
            .collect::<Vec<_>>();
        while let Some((is_end, log)) = queue.pop() {
            let log_idx = tl_mgr.add_log(log);
            log::debug!("{}", self.log_string(&tl_mgr, log_idx));
            if is_end {
                tl_mgr.init_trace(log_idx);
                continue;
            }
            if tl_mgr.get_log_depth(log_idx).unwrap() >= self.config.max_query_depth as isize {
                log::warn!("Query depth exceeds the maximum depth");
                tl_mgr.init_trace(log_idx);
                continue;
            }
            let action = tl_mgr.get_log_action(log_idx).unwrap();
            let query = tl_mgr.get_log_output_query(log_idx).unwrap();
            if action == ActionType::Delegate {
                let next_ns = tl_mgr.get_log_next_ns_ref(log_idx).unwrap();
                if let Some(ns) = self.ns_map.get(next_ns) {
                    queue.par_extend(ns.process_query(log_idx, query.clone(), self, &tl_mgr));
                }
            } else if action == ActionType::RewriteC || action == ActionType::RewriteD {
                queue.par_extend(
                    self.ns_map
                        .par_iter()
                        .map(|(_, ns)| ns.process_query(log_idx, query.clone(), self, &tl_mgr))
                        .flatten(),
                );
            }
        }
        tl_mgr
    }

    /** 随机选取一个第二层的zonefile，添加或者删除几个记录 */
    pub fn random_choose(
        &self,
        nameservers: &[String],
    ) -> (String, usize, Vec<Record>, Vec<Record>) {
        let mut rng = rand::thread_rng();
        // 尝试从非top_ns中随机选取一个ns, 如果没有，就从top_ns中选取
        let non_top_ns = self.ns_map.keys().filter(|ns| !nameservers.contains(ns));
        let ns = if non_top_ns.clone().count() > 0 {
            non_top_ns.choose(&mut rng).unwrap()
        } else {
            nameservers.choose(&mut rng).unwrap()
        };
        let max_origin_len = self
            .ns_map
            .get(ns)
            .unwrap()
            .zones()
            .values()
            .map(|zone| zone.origin().len())
            .max()
            .unwrap();
        log::info!("max_origin_len: {}", max_origin_len);
        // 尝试从ns中随机选取一个zonefile，且该zonefile的origin长度不等于max_origin_len，如果没有，随机
        let unequal_origin = self
            .ns_map
            .get(ns)
            .unwrap()
            .zones()
            .iter()
            .filter(|(_, zone)| zone.origin().len() == max_origin_len);
        let (&zid, zonefile_bdd) = if unequal_origin.clone().count() > 0 {
            let (zid, zonefile_bdd) = unequal_origin.choose(&mut rng).unwrap();
            (zid, zonefile_bdd)
        } else {
            self.ns_map
                .get(ns)
                .unwrap()
                .zones()
                .iter()
                .choose(&mut rng)
                .unwrap()
        };
        // 随机确定需要构造的record数量，最大为max(1, rr数量 * 0.1)
        let upper = (zonefile_bdd.records().len() / 10).max(1).min(10);
        let num_record = rng.gen_range(1..=upper);
        // 生成各个rtype的权重
        let rtypes = vec![
            RecordType::A,
            RecordType::AAAA,
            RecordType::CNAME,
            RecordType::NS,
            RecordType::DNAME,
            RecordType::MX,
            RecordType::TXT,
        ];
        let weights = vec![10, 10, 3, 2, 1, 5, 5];
        let dist = WeightedIndex::new(weights).unwrap();
        let add_rrs: Vec<Record> = (0..num_record)
            .map(|_| {
                let len = rng.gen_range(3..=10);
                let label = Utils::random_label(&mut rng, len);
                let rtype = rtypes[dist.sample(&mut rng)];
                let rdata = match rtype {
                    RecordType::A => format!(
                        "{}.{}.{}.{}",
                        rng.gen_range(0..256),
                        rng.gen_range(0..256),
                        rng.gen_range(0..256),
                        rng.gen_range(0..256)
                    ),
                    RecordType::AAAA => format!(
                        "{:x}:{:x}:{:x}:{:x}:{:x}:{:x}:{:x}:{:x}",
                        rng.gen_range(0..65536),
                        rng.gen_range(0..65536),
                        rng.gen_range(0..65536),
                        rng.gen_range(0..65536),
                        rng.gen_range(0..65536),
                        rng.gen_range(0..65536),
                        rng.gen_range(0..65536),
                        rng.gen_range(0..65536)
                    ),
                    RecordType::CNAME | RecordType::DNAME => {
                        Utils::domain_to_string(&zonefile_bdd.origin())
                    }
                    RecordType::NS => format!(
                        "ns1.{}.{}.net.",
                        label,
                        Utils::domain_to_string(&zonefile_bdd.origin())
                    ),
                    RecordType::MX => format!(
                        "{} {}",
                        rng.gen_range(0..10),
                        format!(
                            "mx{}.{}.net.",
                            label,
                            Utils::domain_to_string(&zonefile_bdd.origin())
                        )
                    ),
                    RecordType::TXT => format!("\"{}\"", label),
                    _ => unreachable!(),
                };
                let mut domain = zonefile_bdd.origin().clone();
                domain.push(label);
                Record::create(domain, rtype, rdata)
            })
            .collect();
        let num_record = rng.gen_range(1..=upper);
        let del_rrs: Vec<Record> = (0..num_record)
            .map(|_| {
                let record_bdd = zonefile_bdd.records().values().choose(&mut rng).unwrap();
                let domain = record_bdd.get_name();
                let rtype = record_bdd.get_rtype();
                let radata = record_bdd.rdata().iter().next().unwrap().clone();
                Record::create(domain.clone(), rtype.clone(), radata)
            })
            .collect();
        (ns.clone(), zid, add_rrs, del_rrs)
    }

    /** 更新 */
    pub fn update_zonefile_rrs(
        &mut self,
        ns: &str,
        zid: usize,
        add_rrs: Vec<Record>,
        del_rrs: Vec<Record>,
    ) -> Result<(), String> {
        self.validate_encoding_update(&add_rrs)?;
        // 第一步更新label_infos
        for record in add_rrs.iter() {
            let domain = record.domain();
            self.update_label_infos(domain);
            if record.rtype() == RecordType::DNAME || record.rtype() == RecordType::CNAME {
                let rdata = record.rdata();
                let data_domain = Utils::string_to_domain(rdata, false);
                self.update_label_infos(&data_domain);
            }
        }
        // SAFETY: self_ref合法，改指针绝对不会操作zonefile_bdd
        let self_ref = unsafe { &*(self as *const LECManager) };
        let zonefile_bdd = self.get_zonefile_bdd_mut(ns, zid).unwrap();

        for record in del_rrs {
            zonefile_bdd.del_record(record, self_ref);
        }
        for record in add_rrs {
            zonefile_bdd.add_record(record, self_ref);
        }
        Ok(())
    }

    pub fn validate_encoding_update(&self, add_rrs: &[Record]) -> Result<(), String> {
        let mut pending: HashMap<usize, HashSet<String>> = HashMap::new();
        let mut domains = Vec::new();
        for record in add_rrs {
            domains.push(record.domain().clone());
            if record.rtype() == RecordType::CNAME || record.rtype() == RecordType::DNAME {
                let target = Utils::string_to_domain(record.rdata(), false);
                if record.rtype() == RecordType::DNAME && record.domain().len() != target.len() {
                    for source_level in record.domain().len()..self.label_infos.len() {
                        let target_level = source_level - record.domain().len() + target.len();
                        if target_level >= self.label_infos.len() {
                            break;
                        }
                        let source = &self.label_infos[source_level];
                        let destination = &self.label_infos[target_level];
                        if source.get_num_bit() != destination.get_num_bit()
                            || !Arc::ptr_eq(source.words_table(), destination.words_table())
                        {
                            return Err(format!(
                                "new DNAME requires incompatible label mapping {source_level}->{target_level}"
                            ));
                        }
                    }
                }
                domains.push(target);
            }
        }

        for domain in domains {
            if domain.len() > self.label_infos.len() {
                return Err(format!(
                    "domain depth {} exceeds allocated depth {}",
                    domain.len(),
                    self.label_infos.len()
                ));
            }
            for (level, label) in domain.iter().enumerate() {
                if label == WILDCARD {
                    continue;
                }
                let info = &self.label_infos[level];
                let table = info.words_table().read().unwrap();
                if table.contains_key(label) {
                    continue;
                }
                let table_id = Arc::as_ptr(info.words_table()) as usize;
                pending.entry(table_id).or_default().insert(label.clone());
            }
        }

        for (table_id, labels) in pending {
            let info = self
                .label_infos
                .iter()
                .find(|info| Arc::as_ptr(info.words_table()) as usize == table_id)
                .unwrap();
            let used = info.words_table().read().unwrap().len();
            let capacity = 1_usize
                .checked_shl(info.get_num_bit() as u32)
                .unwrap_or(usize::MAX);
            if used + labels.len() > capacity {
                return Err(format!(
                    "label table capacity exceeded: need {}, capacity {}",
                    used + labels.len(),
                    capacity
                ));
            }
        }
        Ok(())
    }
}

// getter
#[allow(dead_code)]
impl LECManager {
    pub fn bdd_t(&self) -> &BDDFunction {
        &self.bdd_t
    }

    pub fn bdd_f(&self) -> &BDDFunction {
        &self.bdd_f
    }

    pub fn get_ns_bdd_ref(&self, ns: &str) -> Option<&NameServerBDD> {
        self.ns_map.get(ns)
    }

    pub fn get_zonefile_bdd_ref(&self, ns: &str, zid: usize) -> Option<&ZoneFileBDD> {
        self.get_ns_bdd_ref(ns)
            .and_then(|ns| ns.get_zonefile_bdd_ref(zid))
    }

    pub fn find_zonefile_by_name(&self, file_name: &str) -> Option<(String, usize)> {
        let expected = std::path::Path::new(file_name)
            .file_name()
            .and_then(|name| name.to_str())
            .unwrap_or(file_name);
        for (ns, ns_bdd) in self.ns_map.iter() {
            for (zid, zone) in ns_bdd.zones().iter() {
                let actual = std::path::Path::new(zone.fpath())
                    .file_name()
                    .and_then(|name| name.to_str())
                    .unwrap_or(zone.fpath());
                if actual == expected {
                    return Some((ns.clone(), *zid));
                }
            }
        }
        None
    }

    pub fn get_record_bdd_ref(&self, ns: &str, zid: usize, rid: usize) -> Option<&RecordBDD> {
        self.get_zonefile_bdd_ref(ns, zid)
            .and_then(|zf| zf.get_record_bdd_ref(rid))
    }

    pub fn get_ns_bdd_mut(&mut self, ns: &str) -> Option<&mut NameServerBDD> {
        self.ns_map.get_mut(ns)
    }

    pub fn get_zonefile_bdd_mut(&mut self, ns: &str, zid: usize) -> Option<&mut ZoneFileBDD> {
        self.get_ns_bdd_mut(ns)
            .and_then(|ns| ns.get_zonefile_bdd_mut(zid))
    }
}

// static helper functions
impl LECManager {
    /** 辅助函数，用来初始化时更新label table */
    fn update_label_table(label_tables: &mut Vec<HashMap<String, usize>>, domain: &Domain) {
        for (i, label) in domain.iter().enumerate() {
            if label != WILDCARD {
                // wildcard 不提供任何信息
                let tbl = if i < label_tables.len() {
                    &mut label_tables[i]
                } else {
                    label_tables.last_mut().unwrap()
                };
                if !tbl.contains_key(label) {
                    tbl.insert(label.clone(), tbl.len());
                }
            }
        }
    }

    /**
    输入DNS域名记录，和配置文件，进行预处理
    1. 聚合name和rtype相同的记录
    2. 计算label表，每个label对应一个值
     */
    #[allow(dead_code)]
    fn preprocess_zonefiles(ns2zones: PureNSMap, config: &Config) -> (NSMap, Vec<LabelInfo>) {
        let mut ns2czones: NSMap = HashMap::new();
        let mut label_tables: Vec<HashMap<String, usize>> = vec![HashMap::from([
            ("".to_string(), 0),
            (ALPHA.to_string(), 1),
        ])];
        let mut redundant_labels = 1.max(config.redundant_labels);
        let mut max_num_label = 0_usize;
        // 计算label表格，和聚合records
        for (ns, zones) in ns2zones {
            let mut czones = Vec::with_capacity(zones.len());
            for (fpath, origin, records) in zones {
                let mut crecords: Records = HashMap::new();
                for record in records {
                    let (domain, rtype, rdata) = record.into_tuple();
                    max_num_label = max_num_label.max(domain.len());
                    // Update label tables
                    Self::update_label_table(&mut label_tables, &domain);
                    let rank = Utils::record_rank(&domain, &rtype, &origin);
                    if rtype == RecordType::CNAME || rtype == RecordType::DNAME {
                        // CNAME/DNAME的rdata需要被考虑到词表中
                        let data_domain = Utils::string_to_domain(&rdata, false);
                        max_num_label = max_num_label.max(data_domain.len());
                        if rtype == RecordType::DNAME {
                            redundant_labels =
                                redundant_labels.max(domain.len().abs_diff(data_domain.len()));
                        }
                        Self::update_label_table(&mut label_tables, &data_domain);

                        // 只有DNAME/CNAME会有返回自身值的情况。
                        // 对于负责转发的NS，返回自身是为了转发，而不是给值
                        let rank = match rtype {
                            RecordType::DNAME => 2, // DNAME不可能willcard，直接用2表示普通记录
                            _ => rank - 1,          // CNAME的rank-1表示对应的普通记录/wildcard
                        };
                        let key = (domain.clone(), rtype.clone(), rank);
                        crecords
                            .entry(key)
                            .or_insert(HashSet::new())
                            .insert(rdata.clone());
                    }
                    // Aggregate records with the same domain, rtype, and rank
                    let key = (domain, rtype, rank);
                    crecords.entry(key).or_insert(HashSet::new()).insert(rdata);
                }
                czones.push((fpath, origin, crecords));
            }
            ns2czones.insert(ns, czones);
        }
        // Create label infos
        let num_label = (max_num_label + redundant_labels).max(config.min_label_num);
        let mut start = 0;
        let mut label_infos = Vec::with_capacity(num_label);
        for tbl in label_tables {
            let num_bit = Self::label_bit_width(tbl.len(), config);
            let words_table = Arc::new(RwLock::new(tbl));
            label_infos.push(LabelInfo::new(start, num_bit, words_table));
            start += num_bit;
        }
        // Aggregate label table
        let last_info = label_infos.last().unwrap();
        let last_tbl = last_info.get_words_table();
        let last_num_bit = last_info.get_num_bit();
        for _ in 0..(num_label - label_infos.len()) {
            let words_table = last_tbl.clone();
            label_infos.push(LabelInfo::new(start, last_num_bit, words_table));
            start += last_num_bit;
        }
        (ns2czones, label_infos)
    }

    /** 初始化bdd manager的一些设置 */
    fn bdd_setup(
        total_bits: usize,
        config: &Config,
    ) -> (BDDManagerRef, Vec<BDDFunction>, BDDFunction, BDDFunction) {
        // Initialize BDD manager
        // let node_capacity = 2_usize.saturating_pow(total_bits as u32 + 4);
        let node_capacity = 2_usize.pow(31.min(total_bits as u32 + 4) as u32);
        let cache_capacity = config.bdd_apply_cache_capacity;
        let manager_ref = oxidd::bdd::new_manager(
            node_capacity,
            cache_capacity,
            config
                .bdd_threads
                .try_into()
                .expect("bdd_threads exceeds u32::MAX"),
        );
        let vars = manager_ref.with_manager_exclusive(|manager| {
            (0..total_bits)
                .map(|_| BDDFunction::new_var(manager).unwrap())
                .collect::<Vec<_>>()
        });
        let (bdd_t, bdd_f) = manager_ref
            .with_manager_exclusive(|manager| (BDDFunction::t(manager), BDDFunction::f(manager)));
        (manager_ref, vars, bdd_t, bdd_f)
    }

    fn label_bit_width(value_count: usize, config: &Config) -> usize {
        let exact = if value_count <= 1 {
            1
        } else {
            usize::BITS as usize - (value_count - 1).leading_zeros() as usize
        };
        match config.label_bit_policy {
            LabelBitPolicy::Compact => exact.max(1),
            LabelBitPolicy::Reserved | LabelBitPolicy::Auto => {
                (exact + config.redundant_bits).max(config.min_label_bits)
            }
        }
    }

    /** 加速补丁，用于计算各个label层开始的wildcard, empty, empty+wildcard */
    fn wildcard_bdd_setup(
        label_infos: &Vec<LabelInfo>,
        vars: &Vec<BDDFunction>,
        bdd_t: &BDDFunction,
    ) -> (Vec<BDDFunction>, Vec<BDDFunction>, Vec<BDDFunction>) {
        let mut wildcard_bdd: Vec<BDDFunction> = vec![bdd_t.clone(); label_infos.len()];
        let mut empty_bdd: Vec<BDDFunction> = vec![bdd_t.clone(); label_infos.len()];
        let mut wildcard_empty_bdd: Vec<BDDFunction> = vec![bdd_t.clone(); label_infos.len()];
        // for info in label_infos.iter().rev() {
        for (i, info) in label_infos.iter().enumerate().rev() {
            // 该label层的empty，即所有bit都为0
            let mut label_empty = bdd_t.clone();
            for i in info.get_start()..info.get_end() {
                label_empty = label_empty.and(&vars[i].not().unwrap()).unwrap();
            }
            // 该label层的wildcard，即所有label_wildcard_empty（即true） - label_empty
            let label_wildcard = bdd_t.and(&label_empty.not().unwrap()).unwrap();

            // 从子域到当前的empty = 子域的empty + 当前label层的empty
            empty_bdd[i] = empty_bdd
                .get(i + 1)
                .unwrap_or(&bdd_t)
                .and(&label_empty)
                .unwrap();
            // 从子域到当前的wildcard = 子域的wildcard+empty + 当前label层的wildcard
            wildcard_bdd[i] = wildcard_empty_bdd
                .get(i + 1)
                .unwrap_or(&bdd_t)
                .and(&label_wildcard)
                .unwrap();
            // 从子域到当前的wildcard+empty = (从子域到当前的empty | 从子域到当前的wildcard)
            wildcard_empty_bdd[i] = empty_bdd[i].or(&wildcard_bdd[i]).unwrap();
        }
        (wildcard_bdd, empty_bdd, wildcard_empty_bdd)
    }

    /** 加速补丁，计算各个rtype对应的bdd */
    fn rtype_bdd_setup(
        start: usize,
        vars: &Vec<BDDFunction>,
        bdd_t: &BDDFunction,
        bdd_f: &BDDFunction,
    ) -> HashMap<RecordType, BDDFunction> {
        let mut rtypes = HashMap::new();
        for rtype in RecordType::iter() {
            if rtype == RecordType::ALL {
                continue;
            }
            let rtype_value = rtype as usize;
            let mut rtype_bdd = bdd_t.clone();
            for (i, var) in vars[start..].iter().enumerate() {
                rtype_bdd = match (rtype_value >> i) & 1 {
                    1 => rtype_bdd.and(var).unwrap(),
                    _ => rtype_bdd.and(&var.not().unwrap()).unwrap(),
                }
            }
            rtypes.insert(rtype, rtype_bdd);
        }
        let mut all_bdd = bdd_f.clone();
        for (_, rtype_bdd) in rtypes.iter() {
            all_bdd = all_bdd.or(rtype_bdd).unwrap();
        }
        rtypes.insert(RecordType::ALL, all_bdd);
        rtypes
    }
}

// private methods
impl LECManager {
    /** 根据ns2zones构建lec */
    #[allow(dead_code)]
    fn build_lec(&mut self, ns2czones: NSMap) {
        // ns的lec即所有  zone lec并 不存在是代理问题，zonefile的lec不存在是refuse
        // ns_bdd与zone_bdd关系为 zone_bdd组成ns_bdd；zone_bdd与record_bdd关系为 record_bdd是zone_bdd的子集
        for (ns, zones) in ns2czones {
            self.ns_map
                .insert(ns.clone(), NameServerBDD::build_lec(self, ns, zones));
        }
    }

    /** 将query转为bdd，rtype=None代表rtype取任意值 */
    fn query_to_bdd(&self, name: &Domain, rtype: RecordType) -> BDDResult {
        self.query_to_bdd_manual(name, rtype, 0)
    }

    /** 将query转为bdd，增强版,
     * flag取值：
     * 0：剩余label为empty
     * 1：剩余label为wildcard
     * 2：剩余label为empty+wildcard
     * 3：剩余label不用管
     * 4：剩余label为empty，且rtype取反
     */
    fn query_to_bdd_manual(&self, name: &Domain, rtype: RecordType, flag: usize) -> BDDResult {
        let _profile = ProfileTimer::new(
            self.config.bdd_profile,
            &self.profile_query_encoding_ns,
        );
        self.query_encode_calls.fetch_add(1, Ordering::Relaxed);
        let cache_key = (name.clone(), rtype, flag);
        if self.config.bdd_cache {
            if let Some(cached) = self.query_bdd_cache.read().unwrap().get(&cache_key) {
                self.cache_hits.fetch_add(1, Ordering::Relaxed);
                return Ok(cached.clone());
            }
            self.cache_misses.fetch_add(1, Ordering::Relaxed);
        }

        // Encode rtype
        let mut bdd = if flag != 4 {
            self.rtypes.get(&rtype).unwrap().clone()
        } else {
            self.rtypes
                .get(&RecordType::ALL)
                .unwrap()
                .and(&self.rtypes.get(&rtype).unwrap().not().unwrap())
                .unwrap()
        };
        // Encode name
        for (i, label) in name.iter().enumerate() {
            let info = &self.label_infos[i];
            if label == WILDCARD {
                // 剩下是wildcard
                return bdd.and(&self.wildcard_bdds[i]);
            } else if label == ALPHA {
                // 剩下是empty+wildcard
                return bdd.and(&self.wildcard_empty_bdds[i]);
            } else {
                let value = {
                    let tbl = info.words_table().read().unwrap();
                    *tbl.get(label).unwrap()
                };
                if self.config.label_cube_cache {
                    let label_bdd = self.label_value_bdd(i, value)?;
                    bdd = bdd.and(&label_bdd)?;
                } else {
                    let start = info.get_start();
                    for variable in info.get_start()..info.get_end() {
                        bdd = if (value >> (variable - start)) & 1 == 1 {
                            bdd.and(&self.vars[variable])?
                        } else {
                            bdd.and(&self.vars[variable].not()?)?
                        };
                    }
                }
            }
            // self.check_false(&bdd, format!("encode label {} false", label).as_str());
        }
        // 剩下是根据flag指定的
        let result = match flag {
            0 | 4 => bdd.and(&self.empty_bdds[name.len()]), // 剩下为empty
            1 => bdd.and(&self.wildcard_bdds[name.len()]),  // 剩下为wildcard
            2 => bdd.and(&self.wildcard_empty_bdds[name.len()]), // 剩下为empty+wildcard
            3 => Ok(bdd),                                   // 剩下不用管
            _ => unreachable!(),
        }?;
        if self.config.bdd_cache {
            self.query_bdd_cache
                .write()
                .unwrap()
                .entry(cache_key)
                .or_insert_with(|| result.clone());
        }
        Ok(result)
    }

    fn label_value_bdd(&self, level: usize, value: usize) -> BDDResult {
        if self.config.label_cube_cache {
            if let Some(cached) = self.label_cube_cache[level].read().unwrap().get(&value) {
                self.label_cube_cache_hits
                    .fetch_add(1, Ordering::Relaxed);
                return Ok(cached.clone());
            }
            self.label_cube_cache_misses
                .fetch_add(1, Ordering::Relaxed);
        }

        let info = &self.label_infos[level];
        assert!(
            value < (1_usize << info.get_num_bit()),
            "label value exceeds allocated bit width"
        );
        let mut cube = self.bdd_t.clone();
        for offset in 0..info.get_num_bit() {
            let var = &self.vars[info.get_start() + offset];
            cube = if (value >> offset) & 1 == 1 {
                cube.and(var)?
            } else {
                cube.and(&var.not()?)?
            };
        }
        if self.config.label_cube_cache {
            self.label_cube_cache[level]
                .write()
                .unwrap()
                .entry(value)
                .or_insert_with(|| cube.clone());
        }
        Ok(cube)
    }

    /** 对于一个布尔表达式f(x0,...,xn,xn+1,...,xm)，将其转为f(xn+1,...xm) */
    fn delete_first_n_vars(&self, bdd: &BDDFunction, n: usize) -> BDDFunction {
        let mut ans = bdd.clone();
        loop {
            let level = ans.with_manager_shared(|manager, e| {
                let n = manager.get_node(e);
                n.level()
            }) as usize;
            if level >= n {
                break;
            }
            ans = match ans.cofactor_true().unwrap() {
                // !x0 ^ ... ()
                f if f == self.bdd_f => ans.cofactor_false().unwrap(),
                // x0 ^ ... ()
                f => f,
            }
        }
        ans
    }

    /** 将record转为bdd，返回record对应的bdd以及remain-record_bdd */
    fn record_to_bdd(
        &self,
        name: Domain,
        rtype: RecordType,
        rdata: HashSet<String>,
        rank: usize,
        remain: BDDFunction,
    ) -> (RecordBDD, BDDFunction) {
        let _profile = ProfileTimer::new(
            self.config.bdd_profile,
            &self.profile_record_partition_ns,
        );
        // 计算hit & bdd
        let hit = if rank > 3 {
            let last = match rtype {
                RecordType::NS => 2, // NS最后为alpha
                _ => 1,              // DNAME最后为wildcard
            };
            self.query_to_bdd_manual(&name, RecordType::ALL, last)
                .unwrap()
        } else if rank == 1 || rank == 3 {
            self.query_to_bdd_manual(&name, rtype, 4).unwrap()
        } else {
            self.query_to_bdd(&name, rtype).unwrap()
        };
        let bdd = hit.and(&remain).unwrap();
        // 计算action & action_cache
        let (action, action_cache) = match rtype {
            RecordType::NS if rank > 3 => (ActionType::Delegate, ActionCache::None),
            RecordType::CNAME if rank == 1 || rank == 3 => {
                let name = Utils::string_to_domain(rdata.iter().next().unwrap(), false);
                let cache_bdd = self
                    .query_to_bdd_manual(&name, RecordType::CNAME, 4)
                    .unwrap();
                (ActionType::RewriteC, ActionCache::CNAME(cache_bdd))
            }
            RecordType::DNAME if rank > 3 => {
                let rname = Utils::string_to_domain(rdata.iter().next().unwrap(), false);
                let cache_bdd = self
                    .query_to_bdd_manual(&rname, RecordType::ALL, 3)
                    .unwrap();
                let source_len = name.len();
                let target_len = rname.len();
                let source_boundary = if source_len < self.label_infos.len() {
                    self.label_infos[source_len].get_start()
                } else {
                    self.name_bits
                };
                let mut vars = Vec::new();
                let mut replacements = Vec::new();
                if source_len != target_len {
                    for source_level in source_len..self.label_infos.len() {
                        let target_level = source_level - source_len + target_len;
                        if target_level >= self.label_infos.len() {
                            break;
                        }
                        let source_info = &self.label_infos[source_level];
                        let target_info = &self.label_infos[target_level];
                        assert_eq!(
                            source_info.get_num_bit(),
                            target_info.get_num_bit(),
                            "DNAME-mapped label levels must use equal bit widths"
                        );
                        assert!(
                            Arc::ptr_eq(source_info.words_table(), target_info.words_table()),
                            "DNAME-mapped label levels must share an encoding table"
                        );
                        for offset in 0..source_info.get_num_bit() {
                            vars.push(self.vars[source_info.get_start() + offset].clone());
                            replacements.push(self.vars[target_info.get_start() + offset].clone());
                        }
                    }
                }
                let substitution = Subst::new(vars, replacements);
                let (valid_input_bdd, output_padding_bdd) = if target_len > source_len {
                    let delta = target_len - source_len;
                    (
                        self.empty_bdds[self.label_infos.len() - delta].clone(),
                        self.bdd_t.clone(),
                    )
                } else if source_len > target_len {
                    let delta = source_len - target_len;
                    (
                        self.bdd_t.clone(),
                        self.empty_bdds[self.label_infos.len() - delta].clone(),
                    )
                } else {
                    (self.bdd_t.clone(), self.bdd_t.clone())
                };
                (
                    ActionType::RewriteD,
                    ActionCache::DNAME {
                        substitution,
                        target_bdd: cache_bdd,
                        source_boundary,
                        valid_input_bdd,
                        output_padding_bdd,
                    },
                )
            }
            _ => (ActionType::Answer, ActionCache::None),
        };
        let remain = remain.and(&hit.not().unwrap()).unwrap();
        let retained_hit = self.retain_record_hits.then_some(hit);
        let record_bdd = RecordBDD::new(
            name,
            rtype,
            rank,
            rdata,
            action,
            action_cache,
            retained_hit,
            bdd,
        );
        (record_bdd, remain)
    }

    fn new_query(&self) -> Query {
        Query::new(self.bdd_t.clone(), vec![])
    }

    /** 输入一个bdd表示query，获取这个query中与rtype有关变量的状态
     * 注意：{<a.com, A>, <b.net, AAAA>}最后的rtype是{A, AAAA},虽然两个rtype的name不一样
     */
    fn get_rtype_bdd(&self, bdd: &BDDFunction) -> BDDFunction {
        let mut ans = self.bdd_f().clone();
        for (rtype, rtype_bdd) in self.rtypes.iter() {
            if rtype == &RecordType::ALL {
                continue;
            }
            if bdd.and(rtype_bdd).unwrap() != self.bdd_f {
                ans = ans.or(rtype_bdd).unwrap();
            }
        }
        ans
    }

    /** 命中dname进行重写的操作 */
    fn dname_op(
        &self,
        bdd: &BDDFunction,
        record: &RecordBDD,
    ) -> (BDDFunction, Option<BDDFunction>) {
        if bdd == &self.bdd_f {
            // bdd为false，直接返回false
            return (self.bdd_f.clone(), None);
        }
        // 如果name的小于rdata的长度，且bdd为wildcard，必然出现overflow情况
        let name_len = record
            .name()
            .iter()
            .map(|label| label.len() + 1)
            .sum::<usize>();
        let rdata = record.rdata().iter().next().unwrap();
        let rdata_len = rdata.len();
        let overflow = if name_len < rdata_len {
            // name长度小于rdata长度，overflow
            // TODO: 暂时不实现
            None
        } else {
            None
        };
        let (subst, cache_bdd, source_boundary, valid_input_bdd, output_padding_bdd) =
            record.action_cache().to_dname_cache();
        // 一下流程的例子为query:{<www.a.com, A>, <w2.a.com, TXT>}, record:{<a.com, DNAME, [com]>}
        // 能用下述流程的前提是对于每个dname record，前缀是固定的，也就是说前缀可以抽象层变量的合取，且不包含析取
        // 1. 删除record中的name前缀，query变为{<www.*.*, A>, <w2.*.*, TXT>} (实际上不是*，而是任取)
        let valid_bdd = bdd.and(valid_input_bdd).unwrap();
        let overflow_bdd = bdd.and(&valid_input_bdd.not().unwrap()).unwrap();
        let mut ans_bdd = self.delete_first_n_vars(&valid_bdd, source_boundary);
        // 2. 进行移位（替换），query变为{<www.*, A>, <w2.*, TXT>}
        ans_bdd = ans_bdd.substitute(subst).unwrap();
        // 3. 附上前缀，query变为{<www.com, A>, <w2.com, TXT>}
        ans_bdd = ans_bdd.and(cache_bdd).unwrap();
        ans_bdd = ans_bdd.and(output_padding_bdd).unwrap();
        let bounded_overflow = if overflow_bdd == self.bdd_f {
            None
        } else {
            Some(overflow_bdd)
        };
        (ans_bdd, overflow.or(bounded_overflow))
    }

    /** 辅助函数，增量更新时更新label table */
    fn update_label_infos(&mut self, domain: &Domain) {
        for (i, label) in domain.iter().enumerate() {
            if label != WILDCARD {
                self.label_infos[i].add_word(label);
            }
        }
    }
}

// parallel
#[allow(dead_code)]
impl LECManager {
    fn build_lec_par(&mut self, ns2czones: NSMap) {
        let ns_map = ns2czones
            .into_par_iter()
            .map(|(ns, zones)| (ns.clone(), NameServerBDD::build_lec(self, ns, zones)))
            .collect::<HashMap<_, _>>();
        self.ns_map = ns_map;
    }

    fn preprocess_zonefiles_par(
        ns2zones: PureNSMap,
        config: &Config,
    ) -> (NSMap, Vec<LabelInfo>, Option<usize>) {
        // 分布式处理各个ns对应的zone
        let ns2czones = ns2zones
            .into_par_iter()
            .map(|(ns, zones)| {
                let czones = zones
                    .into_iter()
                    .map(|(fpath, origin, records)| {
                        let crecords =
                            records.into_iter().fold(HashMap::new(), |mut acc, record| {
                                let (domain, rtype, rdata) = record.into_tuple();
                                let rank = Utils::record_rank(&domain, &rtype, &origin);
                                if rtype == RecordType::DNAME || rtype == RecordType::CNAME {
                                    let rank = match rtype {
                                        RecordType::DNAME => 2,
                                        _ => rank - 1,
                                    };
                                    let key = (domain.clone(), rtype.clone(), rank);
                                    acc.entry(key)
                                        .or_insert(HashSet::new())
                                        .insert(rdata.clone());
                                }
                                let key = (domain, rtype, rank);
                                acc.entry(key).or_insert(HashSet::new()).insert(rdata);
                                acc
                            });
                        (fpath, origin, crecords)
                    })
                    .collect::<Vec<_>>();
                (ns, czones)
            })
            .collect::<NSMap>();
        // First determine the bounded depth and the earliest tail that DNAME
        // can shift. All levels in that tail must use compatible encodings.
        let mut max_num_label = 0_usize;
        let mut redundant_labels = 1_usize.max(config.redundant_labels);
        let mut dname_tail_start: Option<usize> = None;
        ns2czones.iter().for_each(|(_, zones)| {
            zones.iter().for_each(|(_, origin, records)| {
                max_num_label = max_num_label.max(origin.len() + 1);
                records.iter().for_each(|((domain, rtype, _), rdatas)| {
                    max_num_label = max_num_label.max(domain.len());
                    if *rtype == RecordType::CNAME || *rtype == RecordType::DNAME {
                        let data_domain =
                            Utils::string_to_domain(rdatas.iter().next().unwrap(), false);
                        max_num_label = max_num_label.max(data_domain.len());
                        if *rtype == RecordType::DNAME {
                            redundant_labels =
                                redundant_labels.max(domain.len().abs_diff(data_domain.len()));
                            if domain.len() != data_domain.len() {
                                let tail_start = domain.len().min(data_domain.len());
                                dname_tail_start = Some(
                                    dname_tail_start
                                        .map_or(tail_start, |current| current.min(tail_start)),
                                );
                            }
                        }
                    }
                });
            });
        });

        let num_label = (max_num_label + redundant_labels).max(config.min_label_num);
        let shared_label_tail_start = match config.label_encoding {
            LabelEncodingMode::Shared => Some(0),
            LabelEncodingMode::PerLayer => dname_tail_start.filter(|start| *start < num_label),
        };
        let table_count = shared_label_tail_start
            .map(|start| start + 1)
            .unwrap_or(num_label);
        let mut label_tables = vec![
            HashMap::from([("".to_string(), 0), (ALPHA.to_string(), 1)]);
            table_count
        ];
        ns2czones.values().for_each(|zones| {
            zones.iter().for_each(|(_, _, records)| {
                records.iter().for_each(|((domain, rtype, _), rdatas)| {
                    Self::update_label_table(&mut label_tables, domain);
                    if *rtype == RecordType::CNAME || *rtype == RecordType::DNAME {
                        let data_domain =
                            Utils::string_to_domain(rdatas.iter().next().unwrap(), false);
                        Self::update_label_table(&mut label_tables, &data_domain);
                    }
                });
            });
        });

        let mut start = 0;
        let mut label_infos = Vec::with_capacity(num_label);
        for tbl in label_tables {
            let num_bit = Self::label_bit_width(tbl.len(), config);
            let words_table = Arc::new(RwLock::new(tbl));
            label_infos.push(LabelInfo::new(start, num_bit, words_table));
            start += num_bit;
        }
        let last_info = label_infos.last().unwrap();
        let last_tbl = last_info.get_words_table();
        let last_num_bit = last_info.get_num_bit();
        let remain_infos = (0..(num_label - label_infos.len()))
            .into_par_iter()
            .map(|i| {
                let start = start + i * last_num_bit;
                LabelInfo::new(start, last_num_bit, last_tbl.clone())
        });
        label_infos.par_extend(remain_infos);
        (ns2czones, label_infos, shared_label_tail_start)
    }

    /** 并行符号化执行 */

    fn process_log(&self, log_idx: usize, tl_mgr: &TraceLogManager) -> Vec<(bool, trace_log::Log)> {
        let action = tl_mgr.get_log_action(log_idx).unwrap();
        let query = tl_mgr.get_log_output_query(log_idx).unwrap();
        let depth = tl_mgr.get_log_depth(log_idx).unwrap() + 1;
        match action {
            ActionType::Delegate => {
                let next_ns = tl_mgr.get_log_next_ns_ref(log_idx).unwrap();
                if let Some(ns) = self.ns_map.get(next_ns) {
                    ns.process_query_par(log_idx, query, self, &tl_mgr)
                } else {
                    // 不存在的NS，认为是发送到一个不管理的NS，返回refuse
                    vec![(
                        true,
                        trace_log::Log::new(
                            0,
                            query,
                            None,
                            ActionType::Refuse,
                            "".to_string(),
                            None,
                            None,
                            None,
                            Some(log_idx),
                            depth,
                        ),
                    )]
                }
            }
            ActionType::RewriteC | ActionType::RewriteD => {
                // 先尝试当前的zonefile_bdd
                let ns = tl_mgr.get_log_ns_ref(log_idx).unwrap();
                let zid = tl_mgr.get_log_zone_idx(log_idx).unwrap();
                let zonefile_bdd = self.get_zonefile_bdd_ref(ns, zid).unwrap();

                let mut bdd = query.bdd().clone();
                let process_bdd = zonefile_bdd.bdd().and(&bdd).unwrap();
                let mut ans = if process_bdd != self.bdd_f {
                    bdd = bdd.and(&process_bdd.not().unwrap()).unwrap();
                    let query = Query::new(process_bdd, query.get_prefix());
                    zonefile_bdd.process_query_par(log_idx, query, self, tl_mgr)
                } else {
                    Vec::new()
                };
                // let (logs, used_bdd) = self
                //     .ns_map
                //     .par_iter()
                //     .filter_map(|(_, ns)| {
                //         let process_bdd = bdd.and(&ns.bdd()).unwrap();
                //         if process_bdd != self.bdd_f {
                //             let query = Query::new(process_bdd.clone(), query.get_prefix());
                //             Some((
                //                 ns.process_query_par(log_idx, query, self, tl_mgr),
                //                 process_bdd,
                //             ))
                //         } else {
                //             None
                //         }
                //     })
                //     .reduce(
                //         || (Vec::new(), self.bdd_f.clone()),
                //         |(mut logs1, used_bdd1), (logs2, used_bdd2)| {
                //             logs1.par_extend(logs2);
                //             (logs1, used_bdd1.or(&used_bdd2).unwrap())
                //         },
                //     );
                // ans.par_extend(logs);
                let mut used_bdd = self.bdd_f.clone();
                for (_, ns) in self.ns_map.iter() {
                    let process_bdd = bdd.and(&ns.bdd()).unwrap();
                    if process_bdd != self.bdd_f {
                        let query = Query::new(process_bdd.clone(), query.get_prefix());
                        let logs = ns.process_query_par(log_idx, query, self, tl_mgr);
                        ans.par_extend(logs);
                        used_bdd = used_bdd.or(&process_bdd).unwrap();
                    }
                }
                let remain = bdd.and(&used_bdd.not().unwrap()).unwrap();
                if remain != self.bdd_f {
                    let log = trace_log::Log::new(
                        0,
                        Query::new(remain, query.get_prefix()),
                        None,
                        ActionType::Refuse,
                        "".to_string(),
                        None,
                        None,
                        None,
                        Some(log_idx),
                        depth,
                    );
                    ans.push((true, log));
                }
                ans
            }
            _ => unreachable!(),
        }
    }

    pub fn symbolic_exec_par(
        &self,
        query: Option<Query>,
        nameservers: &[String],
    ) -> TraceLogManager {
        let query = match query {
            Some(q) => q,
            _ => self.new_query(),
        };
        let mut tl_mgr = TraceLogManager::new(self.config.max_query_depth);
        let log_idx = tl_mgr.new_log(
            query.clone(),
            None,
            ActionType::Delegate,
            "".to_string(),
            None,
            None,
            None,
            None,
        );
        let mut queue = nameservers
            .par_iter()
            .filter_map(|name| {
                if let Some(ns) = self.ns_map.get(name) {
                    Some(ns.process_query_par(log_idx, query.clone(), self, &tl_mgr))
                } else {
                    None
                }
            })
            .flatten()
            .collect::<Vec<_>>();
        while let Some((is_end, log)) = queue.pop() {
            let log_idx = tl_mgr.add_log(log);
            log::debug!("Processing log: {:?}", self.log_string(&tl_mgr, log_idx));
            if is_end {
                tl_mgr.init_trace(log_idx);
                continue;
            }
            if tl_mgr.get_log_depth(log_idx).unwrap() >= self.config.max_query_depth as isize {
                log::warn!("Query depth exceeds the maximum depth");
                tl_mgr.init_trace(log_idx);
                continue;
            }
            queue.par_extend(self.process_log(log_idx, &mut tl_mgr));
        }
        log::info!("Generated {} logs", tl_mgr.get_num_logs());
        log::info!("Generated {} traces", tl_mgr.get_num_traces());
        tl_mgr
    }

    pub fn symbolic_exec_plus_par(
        &self,
        query: Option<Query>,
        nameservers: &[String],
    ) -> TraceLogManager {
        let query = match query {
            Some(q) => q,
            _ => self.new_query(),
        };
        let mut tl_mgr = TraceLogManager::new(self.config.max_query_depth);
        let log_idx = tl_mgr.new_log(
            query.clone(),
            None,
            ActionType::Delegate,
            "".to_string(),
            None,
            None,
            None,
            None,
        );
        let mut queue = nameservers
            .par_iter()
            .filter_map(|name| {
                if let Some(ns) = self.ns_map.get(name) {
                    Some(ns.process_query_par(log_idx, query.clone(), self, &tl_mgr))
                } else {
                    None
                }
            })
            .flatten()
            .collect::<Vec<_>>();
        while !queue.is_empty() {
            let indices = queue
                .into_iter()
                .filter_map(|(is_end, log)| {
                    let log_action = log.get_action();
                    let log_idx = tl_mgr.add_log(log);
                    if is_end {
                        tl_mgr.init_trace(log_idx);
                        return None;
                    }
                    if tl_mgr.get_log_depth(log_idx).unwrap()
                        >= self.config.max_query_depth as isize
                    {
                        log::warn!("Query depth exceeds the maximum depth");
                        tl_mgr.init_trace(log_idx);
                        return None;
                    }
                    match log_action {
                        ActionType::Delegate | ActionType::RewriteC | ActionType::RewriteD => {
                            Some(log_idx)
                        }
                        _ => None,
                    }
                })
                .collect::<Vec<_>>();
            queue = indices
                .into_par_iter()
                .map(|log_idx| self.process_log(log_idx, &tl_mgr))
                .flatten()
                .collect();
        }
        tl_mgr
    }

    /** property checking */
    pub fn property_checking(&self, tl_mgr: &TraceLogManager, jobs: &std::collections::HashSet<String>) -> Vec<String> {
        let errors = tl_mgr.property_checking_par(self);
        let errors = filter_property_errors(errors, jobs);
        if errors.is_empty() {
            log::info!("Property checking passed");
        } else {
            log::info!("Property checking failed");
            for error in &errors {
                log::info!("Error: {}", error);
            }
            log::info!("");
        }
        errors
    }

    /** 为增量验证设计的重新符号化执行 */
    pub fn inc_symbolic_exec_zonefile_par(
        &self,
        ns: &str,
        zid: usize,
        tl_mgr: &mut TraceLogManager,
    ) -> Vec<usize> {
        // 获取该zonefile所有可能处理的query，开始重新处理
        let mut queue = tl_mgr
            .logs()
            .par_iter()
            .filter_map(|(_, log)| {
                if log.ns() != ns || log.get_zone_idx() != zid {
                    return None;
                }
                let prev_log_idx = log.get_prev_log_idx();
                if prev_log_idx == usize::MAX {
                    return None;
                }
                let ns_bdd = self.ns_map.get(ns).unwrap();
                Some(ns_bdd.process_query_par(
                    prev_log_idx,
                    log.input_query().clone(),
                    self,
                    tl_mgr,
                ))
            })
            .flatten()
            .collect::<Vec<_>>();
        // 用于存储新生成的trace的索引
        let mut new_trace_indices = Vec::new();
        while let Some((is_end, log)) = queue.pop() {
            let log_idx = tl_mgr.add_log(log);
            if is_end {
                new_trace_indices.push(tl_mgr.init_trace(log_idx));
                continue;
            }
            if tl_mgr.get_log_depth(log_idx).unwrap() >= self.config.max_query_depth as isize {
                log::warn!("Query depth exceeds the maximum depth");
                new_trace_indices.push(tl_mgr.init_trace(log_idx));
                continue;
            }
            queue.par_extend(self.process_log(log_idx, tl_mgr));
        }
        log::info!("Generated {} traces", new_trace_indices.len());

        new_trace_indices
    }

    /** 为增量验证设计的property checking */
    pub fn inc_property_checking(&self, tl_mgr: &TraceLogManager, idxs: Vec<usize>, jobs: &std::collections::HashSet<String>) -> Vec<String> {
        let errors = tl_mgr.inc_property_checking_par(self, idxs);
        let mut errors = errors.into_iter().collect::<Vec<_>>();
        errors.sort();
        let errors = filter_property_errors(errors, jobs);
        if errors.is_empty() {
            log::info!("Property checking passed");
        } else {
            log::info!("Property checking failed");
            for error in &errors {
                log::info!("Error: {}", error);
            }
            log::info!("");
        }
        errors
    }
}

fn filter_property_errors(errors: Vec<String>, jobs: &std::collections::HashSet<String>) -> Vec<String> {
    errors
        .into_iter()
        .filter(|error| {
            let property = normalize_property_name(error);
            jobs.is_empty() || jobs.contains(property)
        })
        .collect()
}

fn normalize_property_name(error: &str) -> &str {
    match error {
        "hops" => "hops",
        "rewrites" => "rewrites",
        "lame delegation" => "lame_delegation",
        "rewrite blackholing" => "rewrite_blackholing",
        "loop" | "zone loop" => "rewrite_loop",
        "delegation consistency" => "delegation_consistency",
        _ if error.starts_with("rewrite ") => "rewrites",
        _ => error,
    }
}

// debug helper functions
#[allow(dead_code)]
impl LECManager {
    pub(crate) fn profile_start(&self) -> Option<Instant> {
        self.config.bdd_profile.then(Instant::now)
    }

    pub(crate) fn profile_zone_ns_union(&self, start: Option<Instant>) {
        if let Some(start) = start {
            self.profile_zone_ns_union_ns.fetch_add(
                start.elapsed().as_nanos().min(u64::MAX as u128) as u64,
                Ordering::Relaxed,
            );
        }
    }

    pub fn lec_semantic_hash(&self) -> String {
        let mut rows = Vec::new();
        for (ns, ns_bdd) in &self.ns_map {
            for zone in ns_bdd.zones().values() {
                for record in zone.records().values() {
                    let mut rdata = record.rdata().iter().cloned().collect::<Vec<_>>();
                    rdata.sort();
                    rows.push(format!(
                        "{ns}|{}|{}|{:?}|{}|{:?}|{}|{}",
                        zone.fpath(),
                        Utils::domain_to_string(record.name()),
                        record.get_rtype(),
                        record.get_rank(),
                        record.get_action(),
                        rdata.join(";"),
                        record.bdd() != &self.bdd_f,
                    ));
                }
                rows.push(format!(
                    "{ns}|{}|NON_EXIST|{}",
                    zone.fpath(),
                    zone.non_exist() != &self.bdd_f
                ));
            }
        }
        rows.sort();
        Self::hash_rows(&rows)
    }

    pub fn trace_semantic_hash(&self, tl_mgr: &TraceLogManager) -> String {
        let mut traces = tl_mgr
            .trace_paths(None)
            .into_iter()
            .map(|(_, path)| {
                path.into_iter()
                    .map(|log_idx| self.semantic_log_string(tl_mgr, log_idx))
                    .collect::<Vec<_>>()
                    .join("->")
            })
            .collect::<Vec<_>>();
        traces.sort();
        Self::hash_rows(&traces)
    }

    fn hash_rows(rows: &[String]) -> String {
        let mut hasher = Sha256::new();
        for row in rows {
            hasher.update(row.as_bytes());
            hasher.update(b"\n");
        }
        format!("{:x}", hasher.finalize())
    }

    fn semantic_log_string(&self, tl_mgr: &TraceLogManager, idx: usize) -> String {
        let action = tl_mgr.get_log_action(idx).unwrap();
        let ns = tl_mgr.get_log_ns_ref(idx).unwrap();
        let zone_idx = tl_mgr.get_log_zone_idx(idx).unwrap();
        if ns.is_empty() || zone_idx == usize::MAX {
            return format!("{ns}|{:?}", action);
        }
        let zone = self.ns_map.get(ns).unwrap().zones().get(&zone_idx).unwrap();
        let record_idx = tl_mgr.get_log_record_idx(idx).unwrap();
        if record_idx == usize::MAX {
            return format!("{ns}|{}|{:?}", zone.fpath(), action);
        }
        let record = zone.records().get(&record_idx).unwrap();
        let mut rdata = record.rdata().iter().cloned().collect::<Vec<_>>();
        rdata.sort();
        format!(
            "{ns}|{}|{:?}|{}|{:?}|{}|{:?}|{}",
            zone.fpath(),
            action,
            Utils::domain_to_string(record.name()),
            record.get_rtype(),
            rdata.join(";"),
            tl_mgr.get_log_next_ns_ref(idx),
            tl_mgr.get_log_depth(idx).unwrap(),
        )
    }

    pub fn dump_lecs<W: Write>(&self, writer: &mut W) -> std::io::Result<()> {
        writeln!(writer, "===== LEC TABLE =====")?;
        let mut ns_entries = self.ns_map.iter().collect::<Vec<_>>();
        ns_entries.sort_by(|a, b| a.0.cmp(b.0));
        for (ns, ns_bdd) in ns_entries {
            writeln!(writer, "NS {}", ns)?;
            let mut zones = ns_bdd.zones().iter().collect::<Vec<_>>();
            zones.sort_by(|a, b| a.0.cmp(b.0));
            for (zid, zone) in zones {
                writeln!(writer, "  Zone[{}] {}", zid, zone.fpath())?;
                let mut records = zone.records().iter().collect::<Vec<_>>();
                records.sort_by(|a, b| {
                    a.1.get_rank()
                        .cmp(&b.1.get_rank())
                        .then_with(|| Utils::domain_to_string(a.1.name()).cmp(&Utils::domain_to_string(b.1.name())))
                });
                for (rid, record) in records {
                    writeln!(
                        writer,
                        "    LEC record_idx={} active={} rank={} action={:?} owner={} type={:?} rdata={:?}",
                        rid,
                        record.bdd() != &self.bdd_f,
                        record.get_rank(),
                        record.get_action(),
                        Utils::domain_to_string(record.name()),
                        record.get_rtype(),
                        record.rdata()
                    )?;
                }
                writeln!(
                    writer,
                    "    LEC non_exist active={} origin={}",
                    zone.hit() != &self.bdd_f,
                    Utils::domain_to_string(zone.origin())
                )?;
            }
        }
        writeln!(writer)?;
        Ok(())
    }

    pub fn dump_traces<W: Write>(
        &self,
        writer: &mut W,
        tl_mgr: &TraceLogManager,
        trace_indices: Option<&[usize]>,
        title: &str,
    ) -> std::io::Result<()> {
        writeln!(writer, "===== {} =====", title)?;
        writeln!(
            writer,
            "logs={} traces={}",
            tl_mgr.get_num_logs(),
            tl_mgr.get_num_traces()
        )?;
        for (trace_idx, path) in tl_mgr.trace_paths(trace_indices) {
            writeln!(writer, "Trace[{}]", trace_idx)?;
            for log_idx in path {
                writeln!(writer, "  {}", self.log_string(tl_mgr, log_idx))?;
            }
        }
        writeln!(writer)?;
        Ok(())
    }

    pub fn print_num_lec(&self) {
        let mut ns2zonelec = HashMap::new();
        for (ns, ns_bdd) in self.ns_map.iter() {
            log::debug!("NS: {}", ns);
            ns2zonelec.insert(ns.clone(), Vec::new());
            for (_, zone) in ns_bdd.zones().iter() {
                log::debug!("  Zone: {}", zone.fpath());
                let mut count = 0;
                let mut data = zone.records().values().collect::<Vec<_>>();
                data.sort_by(|a, b| a.get_rank().cmp(&b.get_rank()));
                for record in data {
                    log::debug!(
                        "    Record ({}, {:?}, {:?}) - {} - rank: {}",
                        Utils::domain_to_string(record.name()),
                        record.get_rtype(),
                        record.rdata(),
                        record.bdd() != &self.bdd_f,
                        record.get_rank()
                    );
                    if record.bdd() != &self.bdd_f {
                        count += 1;
                    }
                }
                log::debug!("    Refuse: {}", zone.hit() != &self.bdd_f);
                if zone.hit() != &self.bdd_f {
                    count += 1;
                }
                log::debug!("    Total: {}", count);
                ns2zonelec
                    .get_mut(ns)
                    .unwrap()
                    .push((zone.fpath().clone(), count));
            }
        }

        // 按照ns名字排序
        log::debug!("");
        let mut ns2zonelec = ns2zonelec.into_iter().collect::<Vec<_>>();
        ns2zonelec.sort_by(|a, b| a.0.cmp(&b.0));
        for (ns, mut zones) in ns2zonelec {
            log::debug!("NS: {}", ns);
            // 按照zone名字排序
            zones.sort_by(|a, b| a.0.cmp(&b.0));
            for (zone, count) in zones {
                log::debug!("  Zone: {} - {}", zone, count);
            }
        }
    }

    fn log_bdd(&self, bdd: &BDDFunction) {
        let mut cursor = Cursor::new(Vec::new());
        let _ = self.manager_ref.with_manager_exclusive(|manager| {
            dddmp::export(
                &mut cursor,
                manager,
                true,
                "oxidd",
                self.vars.iter().collect::<Vec<_>>().as_slice(),
                None,
                &[bdd],
                None,
                |_| false,
            )
            .unwrap();
        });
        let string = std::str::from_utf8(&cursor.get_ref()).unwrap();
        log::debug!("{}", string);
    }

    fn log_string(&self, tl_mgr: &TraceLogManager, idx: usize) -> String {
        let action = tl_mgr.get_log_action(idx).unwrap();
        let ns = tl_mgr.get_log_ns_ref(idx).unwrap();
        if ns.is_empty() {
            return format!("Log[{}]: {{ ns: {}, action: {:?} }}", idx, ns, action);
        }
        let ns_bdd = self.ns_map.get(ns).unwrap();
        let zone_idx = tl_mgr.get_log_zone_idx(idx).unwrap();
        if zone_idx == usize::MAX {
            return format!("Log[{}]: {{ ns: {}, action: {:?} }}", idx, ns, action);
        }
        let zone = ns_bdd.zones().get(&zone_idx).unwrap();
        let zone_name = zone.fpath().split('/').last().unwrap();
        let record_idx = tl_mgr.get_log_record_idx(idx).unwrap();
        if record_idx == usize::MAX {
            return format!(
                "Log[{}]: {{ ns: {}, zone: {}, action: {:?} }}",
                idx, ns, zone_name, action
            );
        }
        let record = zone.records().get(&record_idx).unwrap();

        format!(
            "Log[{}]: {{ ns: {}, zone: {}, action: {:?}, record: ({}, {:?}, {:?}), next_ns: {:?}, prev_log_idx: {}, depth: {} }}",
            idx,
            ns,
            zone_name,
            action,
            Utils::domain_to_string(record.name()),
            record.get_rtype(),
            record.rdata(),
            tl_mgr.get_log_next_ns_ref(idx),
            tl_mgr.get_log_prev_log_idx(idx).unwrap(),
            tl_mgr.get_log_depth(idx).unwrap()
        )
    }

    fn preprocess_zonefiles_cmp(ns2zones: PureNSMap, config: &Config) {
        let mut times = [0_f64; 10];
        for i in 0..10 {
            let ns2zones = ns2zones.clone();
            let start = chrono::Utc::now();
            Self::preprocess_zonefiles(ns2zones, config);
            let duration = chrono::Utc::now()
                .signed_duration_since(start)
                .num_microseconds()
                .unwrap() as f64
                / 1000.0;
            times[i] = duration;
        }
        log::info!(
            "Preprocess zonefiles times {:?}, 
            avg: {}",
            times,
            times.iter().sum::<f64>() / 10.0
        );
        for i in 0..10 {
            let ns2zones = ns2zones.clone();
            let start = chrono::Utc::now();
            Self::preprocess_zonefiles_par(ns2zones, config);
            let duration = chrono::Utc::now()
                .signed_duration_since(start)
                .num_microseconds()
                .unwrap() as f64
                / 1000.0;
            times[i] = duration;
        }
        log::info!(
            "Preprocess zonefiles par times {:?}, 
            avg: {}",
            times,
            times.iter().sum::<f64>() / 10.0
        );
    }

    fn build_lec_cmp(&mut self, ns2czones: NSMap) {
        let mut times = [0_f64; 10];
        for i in 0..10 {
            let ns2czones = ns2czones.clone();
            let start = chrono::Utc::now();
            self.build_lec(ns2czones);
            let duration = chrono::Utc::now()
                .signed_duration_since(start)
                .num_microseconds()
                .unwrap() as f64
                / 1000.0;
            times[i] = duration;
        }
        log::info!(
            "Build lec times {:?}, 
            avg: {}",
            times,
            times.iter().sum::<f64>() / 10.0
        );
        for i in 0..10 {
            let ns2czones = ns2czones.clone();
            let start = chrono::Utc::now();
            self.build_lec_par(ns2czones);
            let duration = chrono::Utc::now()
                .signed_duration_since(start)
                .num_microseconds()
                .unwrap() as f64
                / 1000.0;
            times[i] = duration;
        }
        log::info!(
            "Build lec par times {:?}, 
            avg: {}",
            times,
            times.iter().sum::<f64>() / 10.0
        );
    }

    fn check_false(&self, bdd: &BDDFunction, msg: &str) {
        if bdd == &self.bdd_f {
            log::error!("{}", msg);
        }
    }
}
