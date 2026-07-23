use super::{
    action::ActionType,
    query::Query,
    record_bdd::RecordBDD,
    trace_log::{self, TraceLogManager},
    LECManager,
};
use crate::{
    record::{Record, RecordType},
    utils::Utils,
};
use oxidd::{bdd::BDDFunction, BooleanFunction};
use rayon::prelude::*;
use std::{
    collections::{HashMap, HashSet},
    usize,
};

pub struct ZoneFileBDD {
    ns: String,

    idx: usize,
    fpath: String,
    origin: Vec<String>,
    hit: BDDFunction,
    bdd: BDDFunction,
    non_exist: BDDFunction,

    record_idx: usize,
    records: HashMap<usize, RecordBDD>,
    ip_map: HashMap<String, HashSet<String>>,
}

#[allow(dead_code)]
impl ZoneFileBDD {
    pub fn ns(&self) -> &String {
        &self.ns
    }

    pub fn fpath(&self) -> &String {
        &self.fpath
    }

    pub fn get_fpath(&self) -> String {
        self.fpath.clone()
    }

    pub fn origin(&self) -> &Vec<String> {
        &self.origin
    }

    pub fn get_origin(&self) -> Vec<String> {
        self.origin.clone()
    }

    pub fn hit(&self) -> &BDDFunction {
        &self.hit
    }

    pub fn bdd(&self) -> &BDDFunction {
        &self.bdd
    }

    pub fn non_exist(&self) -> &BDDFunction {
        &self.non_exist
    }

    pub fn records(&self) -> &HashMap<usize, RecordBDD> {
        &self.records
    }

    pub fn ip_map(&self) -> &HashMap<String, HashSet<String>> {
        &self.ip_map
    }

    pub fn get_record_bdd_ref(&self, idx: usize) -> Option<&RecordBDD> {
        self.records.get(&idx)
    }

    pub fn get_ip_ref(&self, domain: &str) -> Option<&HashSet<String>> {
        self.ip_map.get(domain)
    }
}

impl ZoneFileBDD {
    pub fn build_lec(
        lec_mgr: &LECManager,
        ns: String,
        idx: usize,
        fpath: String,
        origin: Vec<String>,
        records: super::Records,
        zone_remain: &BDDFunction,
    ) -> Self {
        // Sort records by rank in ascending order
        let mut ordered_records = records.into_iter().collect::<Vec<_>>();
        ordered_records.par_sort_by(|(k1, _), (k2, _)| k2.2.cmp(&k1.2));
        let zone_hit = lec_mgr
            .query_to_bdd_manual(&origin, RecordType::ALL, 2)
            .unwrap();
        // calculate the zone_bdd, update zone_remain and ns_bdd
        let zone_bdd = zone_remain.and(&zone_hit).unwrap();
        // let mut zonefile_bdd = ZoneFileBDD::new(ns, idx, fpath, origin, zone_hit, zone_bdd);
        let mut record_remain = zone_bdd.clone();
        let mut records = HashMap::new();
        let mut ip_map = HashMap::new();
        let mut ridx = 0;
        for ((domain, rtype, rank), rdata) in ordered_records {
            let (record_bdd, remain) =
                lec_mgr.record_to_bdd(domain, rtype, rdata, rank, record_remain);
            record_remain = remain;
            if record_bdd.get_rtype() == RecordType::A || record_bdd.get_rtype() == RecordType::AAAA
            {
                let key = Utils::domain_to_string(record_bdd.name());
                let value = record_bdd.get_rdata();
                ip_map.entry(key).or_insert_with(HashSet::new).extend(value);
            }
            records.insert(ridx, record_bdd);
            ridx += 1;
        }

        ZoneFileBDD {
            ns,
            idx,
            fpath,
            origin,
            hit: zone_hit,
            bdd: zone_bdd,
            non_exist: record_remain,
            record_idx: ridx,
            records,
            ip_map,
        }
    }

    /** 增量验证的methods */
    fn _add_record(&mut self, record: Record, rank: usize, lec_mgr: &LECManager) {
        let (domain, rtype, rdata) = record.into_tuple();
        // 同时获取所有优先级更低的records，还有其可用空间
        let mut low_records = Vec::new();
        let mut remain = self.non_exist.clone();
        for record in self.records.values_mut() {
            if *record.name() == domain && record.get_rtype() == rtype && record.get_rank() == rank
            {
                // 如果有完全一样的name和rtype的record，直接添加
                record.add_rdata(rdata);
                return;
            }
            if record.get_rank() < rank {
                // 可以从rank低的record中夺取空间
                remain = remain.or(&record.bdd()).unwrap();
                low_records.push(record);
            }
        }
        // 计算record的hit
        let (record_bdd, remain) =
            lec_mgr.record_to_bdd(domain, rtype, HashSet::from([rdata]), rank, remain);

        if remain.and(&self.non_exist.not().unwrap()).unwrap() == *lec_mgr.bdd_f() {
            // 如果不只从non_exist那空间，需要更新lower records
            for record in low_records {
                record.del_bdd(record_bdd.bdd());
            }
        }
        self.non_exist = self
            .non_exist
            .and(&record_bdd.bdd().not().unwrap())
            .unwrap();
        // 添加到records中
        let ridx = self.record_idx;
        self.records.insert(ridx, record_bdd);
        self.record_idx += 1;
    }

    pub fn add_record(&mut self, record: Record, lec_mgr: &LECManager) {
        let rtype = record.rtype();
        let rank = Utils::record_rank(record.domain(), &rtype, &self.origin);
        if rtype == RecordType::CNAME || rtype == RecordType::DNAME {
            let opt_rank = match rtype {
                RecordType::DNAME => 2,
                _ => rank - 1,
            };
            self._add_record(record.clone(), opt_rank, lec_mgr);
        }
        self._add_record(record, rank, lec_mgr);
    }

    fn _del_record(&mut self, record: Record, rank: usize, lec_mgr: &LECManager) {
        let (domain, rtype, rdata) = record.into_tuple();
        let mut low_records = Vec::new();
        let mut remain = lec_mgr.bdd_f().clone();
        let mut del_idx = usize::MAX;
        for (&idx, record) in self.records.iter_mut() {
            if *record.name() == domain && record.get_rtype() == rtype && record.get_rank() == rank
            {
                record.del_rdata(&rdata);
                if record.rdata().is_empty() {
                    remain = record.bdd().clone();
                    del_idx = idx;
                }
                break;
            }
            if record.get_rank() < rank {
                low_records.push(record);
            }
        }
        if del_idx == usize::MAX {
            return;
        }
        // 如果完整的删除了record，需要更新lower records
        for record in low_records {
            remain = record.add_bdd(&remain);
        }
        self.non_exist = self.non_exist.or(&remain).unwrap();
        self.records.remove(&del_idx);
    }

    pub fn del_record(&mut self, record: Record, lec_mgr: &LECManager) {
        let rtype = record.rtype();
        let rank = Utils::record_rank(record.domain(), &rtype, &self.origin);
        if rtype == RecordType::CNAME || rtype == RecordType::DNAME {
            let opt_rank = match rtype {
                RecordType::DNAME => 2,
                _ => rank - 1,
            };
            self._del_record(record.clone(), opt_rank, lec_mgr);
        }
        self._del_record(record, rank, lec_mgr);
    }

    /** 处理查询，并且返回生成的log indices
     * Note: 仅能由NS调用，query 必须是 bdd 的子集
     */
    pub fn process_query(
        &self,
        prev_log_idx: usize,
        query: Query,
        lec_mgr: &LECManager,
        tl_mgr: &TraceLogManager,
    ) -> Vec<(bool, trace_log::Log)> {
        let mut remain_bdd = query.bdd().clone();
        if remain_bdd == *lec_mgr.bdd_f() {
            return Vec::new();
        }
        let depth = tl_mgr.get_log_depth(prev_log_idx).unwrap() + 1;
        let mut logs = Vec::new();
        let mut used_bdd = lec_mgr.bdd_f().clone();
        let mut times = Vec::new();
        for (&r_idx, record) in self.records() {
            let record_bdd = record.bdd();
            let match_bdd = remain_bdd.and(record_bdd).unwrap();
            if match_bdd == *lec_mgr.bdd_f() {
                continue;
            }
            used_bdd = used_bdd.or(&match_bdd).unwrap();
            match record.get_action() {
                ActionType::Answer => {
                    let log = trace_log::Log::new(
                        0,
                        Query::new(match_bdd, record.get_concrete_name()),
                        None,
                        ActionType::Answer,
                        self.ns.clone(),
                        Some(self.idx),
                        Some(r_idx),
                        None,
                        Some(prev_log_idx),
                        depth,
                    );
                    logs.push((true, log));
                }
                ActionType::Delegate => {
                    for ns in record.get_rdata() {
                        let log = trace_log::Log::new(
                            0,
                            Query::new(match_bdd.clone(), record.get_concrete_name()),
                            None,
                            ActionType::Delegate,
                            self.ns.clone(),
                            Some(self.idx),
                            Some(r_idx),
                            Some(ns),
                            Some(prev_log_idx),
                            depth,
                        );
                        logs.push((false, log));
                    }
                }
                ActionType::RewriteC => {
                    let start = chrono::Utc::now();
                    let rtype_bdd = lec_mgr.get_rtype_bdd(&match_bdd);
                    let dur = chrono::Utc::now()
                        .signed_duration_since(start)
                        .num_microseconds()
                        .unwrap() as f64
                        / 1000.0;
                    times.push(dur);
                    let name_bdd = record.action_cache().get_rdata_bdd();
                    let output_query = Query::new(
                        rtype_bdd.and(name_bdd).unwrap(),
                        Utils::string_to_domain(record.rdata().iter().next().unwrap(), false),
                    );
                    let log = trace_log::Log::new(
                        0,
                        Query::new(match_bdd, record.get_concrete_name()),
                        Some(output_query),
                        ActionType::RewriteC,
                        self.ns.clone(),
                        Some(self.idx),
                        Some(r_idx),
                        None,
                        Some(prev_log_idx),
                        depth,
                    );
                    logs.push((false, log));
                }
                ActionType::RewriteD => {
                    let (out1_bdd, out2_bdd) = lec_mgr.dname_op(&match_bdd, record);
                    let prefix =
                        Utils::string_to_domain(record.rdata().iter().next().unwrap(), false);
                    let log = trace_log::Log::new(
                        0,
                        Query::new(match_bdd.clone(), record.get_concrete_name()),
                        Some(Query::new(out1_bdd, prefix)),
                        ActionType::RewriteD,
                        self.ns.clone(),
                        Some(self.idx),
                        Some(r_idx),
                        None,
                        Some(prev_log_idx),
                        depth,
                    );
                    logs.push((false, log));
                    if let Some(out2_bdd) = out2_bdd {
                        let prefix =
                            Utils::string_to_domain(record.rdata().iter().next().unwrap(), false);
                        let log = trace_log::Log::new(
                            0,
                            Query::new(match_bdd, record.get_concrete_name()),
                            Some(Query::new(out2_bdd, prefix)),
                            ActionType::RewriteD,
                            self.ns.clone(),
                            Some(self.idx),
                            Some(r_idx),
                            None,
                            Some(prev_log_idx),
                            depth,
                        );
                        logs.push((true, log));
                    }
                }
                _ => (),
            }
        }
        remain_bdd = remain_bdd.and(&used_bdd.not().unwrap()).unwrap();
        if remain_bdd != *lec_mgr.bdd_f() {
            let log = trace_log::Log::new(
                0,
                Query::new(remain_bdd, query.get_prefix()),
                None,
                ActionType::NonExist,
                self.ns.clone(),
                Some(self.idx),
                None,
                None,
                Some(prev_log_idx),
                depth,
            );
            logs.push((true, log));
        }
        logs
    }
}

const BUNCH_SIZE: usize = 2000;

/** 以下代码为多线程代码 */
// #[allow(dead_code)]
impl ZoneFileBDD {
    /** 基于map reduce思想的多线程 */
    pub fn process_query_par(
        &self,
        prev_log_idx: usize,
        query: Query,
        lec_mgr: &LECManager,
        tl_mgr: &TraceLogManager,
    ) -> Vec<(bool, trace_log::Log)> {
        let remain_bdd = query.bdd().clone();
        if remain_bdd == *lec_mgr.bdd_f() {
            return Vec::new();
        }
        let records = self.records().iter().collect::<Vec<_>>();
        let depth = tl_mgr.get_log_depth(prev_log_idx).unwrap() + 1;
        let mut logs = records
            .par_chunks(BUNCH_SIZE)
            .map(|records| {
                let mut logs = Vec::new();
                for (&r_idx, record) in records {
                    if !Utils::is_pre_match(record.name(), query.prefix()) {
                        continue;
                    }
                    let record_bdd = record.bdd();
                    let match_bdd = remain_bdd.and(record_bdd).unwrap();
                    if match_bdd == *lec_mgr.bdd_f() {
                        continue;
                    }
                    match record.get_action() {
                        ActionType::Answer => {
                            let log = trace_log::Log::new(
                                0,
                                Query::new(match_bdd, record.get_concrete_name()),
                                None,
                                ActionType::Answer,
                                self.ns.clone(),
                                Some(self.idx),
                                Some(r_idx),
                                None,
                                Some(prev_log_idx),
                                depth,
                            );
                            logs.push((true, log));
                        }
                        ActionType::Delegate => {
                            for ns in record.get_rdata() {
                                let log = trace_log::Log::new(
                                    0,
                                    Query::new(match_bdd.clone(), record.get_concrete_name()),
                                    None,
                                    ActionType::Delegate,
                                    self.ns.clone(),
                                    Some(self.idx),
                                    Some(r_idx),
                                    Some(ns),
                                    Some(prev_log_idx),
                                    depth,
                                );
                                logs.push((false, log));
                            }
                        }
                        ActionType::RewriteC => {
                            let rtype_bdd = lec_mgr.get_rtype_bdd(&match_bdd);
                            let name_bdd = record.action_cache().get_rdata_bdd();
                            let prefix = Utils::string_to_domain(
                                record.rdata().iter().next().unwrap(),
                                false,
                            );
                            let output_query = Query::new(rtype_bdd.and(name_bdd).unwrap(), prefix);
                            let log = trace_log::Log::new(
                                0,
                                Query::new(match_bdd, record.get_concrete_name()),
                                Some(output_query),
                                ActionType::RewriteC,
                                self.ns.clone(),
                                Some(self.idx),
                                Some(r_idx),
                                None,
                                Some(prev_log_idx),
                                depth,
                            );
                            logs.push((false, log));
                        }
                        ActionType::RewriteD => {
                            let (out1_bdd, out2_bdd) = lec_mgr.dname_op(&match_bdd, record);
                            let prefix = Utils::string_to_domain(
                                record.rdata().iter().next().unwrap(),
                                false,
                            );
                            let log = trace_log::Log::new(
                                0,
                                Query::new(match_bdd.clone(), record.get_concrete_name()),
                                Some(Query::new(out1_bdd, prefix)),
                                ActionType::RewriteD,
                                self.ns.clone(),
                                Some(self.idx),
                                Some(r_idx),
                                None,
                                Some(prev_log_idx),
                                depth,
                            );
                            logs.push((false, log));
                            if let Some(out2_bdd) = out2_bdd {
                                let prefix = Utils::string_to_domain(
                                    record.rdata().iter().next().unwrap(),
                                    false,
                                );
                                let log = trace_log::Log::new(
                                    0,
                                    Query::new(match_bdd, record.get_concrete_name()),
                                    Some(Query::new(out2_bdd, prefix)),
                                    ActionType::RewriteD,
                                    self.ns.clone(),
                                    Some(self.idx),
                                    Some(r_idx),
                                    None,
                                    Some(prev_log_idx),
                                    depth,
                                );
                                logs.push((true, log));
                            }
                        }
                        _ => (),
                    }
                }
                logs
            })
            .reduce(
                || Vec::new(),
                |acc_logs, logs| acc_logs.into_iter().chain(logs).collect(),
            );
        let non_exist_bdd = remain_bdd.and(&self.non_exist).unwrap();
        if non_exist_bdd != *lec_mgr.bdd_f() {
            let log = trace_log::Log::new(
                0,
                Query::new(non_exist_bdd, query.get_prefix()),
                None,
                ActionType::NonExist,
                self.ns.clone(),
                Some(self.idx),
                None,
                None,
                Some(prev_log_idx),
                depth,
            );
            logs.push((true, log));
        }
        logs
    }
}
