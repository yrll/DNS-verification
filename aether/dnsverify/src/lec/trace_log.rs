use super::action::ActionType;
use super::query::Query;
use super::LECManager;
use super::Utils;
use oxidd::{bdd::BDDFunction, BooleanFunction};
use rayon::prelude::*;
use std::collections::{HashMap, HashSet};

#[derive(Clone)]
pub struct Log {
    idx: usize,
    input_query: Query,
    output_query: Option<Query>,
    action: ActionType,
    ns: String,
    zone_idx: usize,
    record_idx: usize,
    next_ns: Option<String>, // 仅仅用来辅助NS代理转发，CNAME和DNAME重写不会用到这个

    prev_log_idx: usize,
    depth: isize,
}

#[allow(dead_code)]
impl Log {
    pub fn new(
        idx: usize,
        input_query: Query,
        output_query: Option<Query>,
        action: ActionType,
        ns: String,
        zone_idx: Option<usize>,
        record_idx: Option<usize>,
        next_ns: Option<String>,
        prev_log_idx: Option<usize>,
        depth: isize,
    ) -> Self {
        Log {
            idx,
            input_query,
            output_query,
            action,
            ns,
            zone_idx: zone_idx.unwrap_or(usize::MAX),
            record_idx: record_idx.unwrap_or(usize::MAX),
            next_ns,
            prev_log_idx: prev_log_idx.unwrap_or(usize::MAX),
            depth,
        }
    }

    pub fn get_idx(&self) -> usize {
        self.idx
    }

    pub fn input_query(&self) -> &Query {
        &self.input_query
    }

    pub fn output_query(&self) -> &Query {
        if let Some(output_query) = &self.output_query {
            output_query
        } else {
            &self.input_query
        }
    }

    pub fn get_action(&self) -> ActionType {
        self.action
    }

    pub fn ns(&self) -> &String {
        &self.ns
    }

    pub fn get_zone_idx(&self) -> usize {
        self.zone_idx
    }

    pub fn get_record_idx(&self) -> usize {
        self.record_idx
    }

    pub fn next_ns(&self) -> Option<&String> {
        self.next_ns.as_ref()
    }

    pub fn get_prev_log_idx(&self) -> usize {
        self.prev_log_idx
    }

    pub fn get_depth(&self) -> isize {
        self.depth
    }

    pub fn has_intersection(&self, other: &Log, bdd_f: &BDDFunction) -> bool {
        self.ns() == other.ns()
            && self.zone_idx == other.zone_idx
            && self
                .input_query()
                .bdd()
                .and(other.input_query().bdd())
                .unwrap()
                != *bdd_f
    }

    pub fn set_idx(&mut self, idx: usize) {
        self.idx = idx;
    }
}

struct Trace {
    end_log_idx: usize,
}

impl Trace {
    pub fn new(end_log_idx: usize) -> Self {
        Trace { end_log_idx }
    }
}

#[allow(dead_code)]
pub struct TraceLogManager {
    log_idx: usize,
    logs: HashMap<usize, Log>,

    max_log_depth: usize,
    traces: Vec<Trace>,
}

// 与Log相关的方法
impl TraceLogManager {
    pub fn new(max_log_depth: usize) -> Self {
        TraceLogManager {
            log_idx: 0,
            logs: HashMap::new(),

            max_log_depth,
            traces: Vec::new(),
        }
    }

    pub fn new_log(
        &mut self,
        input_query: Query,
        output_query: Option<Query>,
        action: ActionType,
        ns: String,
        zone_idx: Option<usize>,
        record_idx: Option<usize>,
        next_ns: Option<String>,
        prev_log_idx: Option<usize>,
    ) -> usize {
        let log = Log::new(
            self.log_idx,
            input_query,
            output_query,
            action,
            ns,
            zone_idx,
            record_idx,
            next_ns,
            prev_log_idx,
            self.get_log_depth(prev_log_idx.unwrap_or(usize::MAX))
                .unwrap_or(-1)
                + 1,
        );
        self.add_log(log)
    }

    pub fn add_log(&mut self, mut log: Log) -> usize {
        log.set_idx(self.log_idx);
        self.logs.insert(self.log_idx, log);
        self.log_idx += 1;
        self.log_idx - 1
    }

    pub fn get_num_logs(&self) -> usize {
        self.logs.len()
    }

    pub fn logs(&self) -> &HashMap<usize, Log> {
        &self.logs
    }
}

// Getter methods for Log
impl TraceLogManager {
    pub fn get_log_output_query(&self, idx: usize) -> Result<Query, ()> {
        self.logs
            .get(&idx)
            .map(|log| log.output_query().clone())
            .ok_or(())
    }

    pub fn get_log_action(&self, idx: usize) -> Option<ActionType> {
        self.logs.get(&idx).map(|log| log.get_action())
    }

    pub fn get_log_ns_ref(&self, idx: usize) -> Option<&String> {
        self.logs.get(&idx).map(|log| log.ns())
    }

    pub fn get_log_zone_idx(&self, idx: usize) -> Option<usize> {
        self.logs.get(&idx).map(|log| log.get_zone_idx())
    }

    pub fn get_log_record_idx(&self, idx: usize) -> Option<usize> {
        self.logs.get(&idx).map(|log| log.get_record_idx())
    }

    pub fn get_log_next_ns_ref(&self, idx: usize) -> Option<&String> {
        self.logs.get(&idx).and_then(|log| log.next_ns())
    }

    pub fn get_log_prev_log_idx(&self, idx: usize) -> Option<usize> {
        self.logs.get(&idx).map(|log| log.get_prev_log_idx())
    }

    pub fn get_log_depth(&self, idx: usize) -> Option<isize> {
        self.logs.get(&idx).map(|log| log.get_depth())
    }
}

// 与Trace相关的方法
impl TraceLogManager {
    pub fn init_trace(&mut self, log_idx: usize) -> usize {
        let trace = Trace::new(log_idx);
        self.traces.push(trace);
        self.traces.len() - 1
    }

    /** 获取从log_idx反推的整条trace上所有(ns, zid)出现过的query，用于检查循环 */
    pub fn get_dup_bdd(&self, log_idx: usize, ns: &str, bdd_f: &BDDFunction) -> BDDFunction {
        let mut bdd = bdd_f.clone();
        let mut cur_idx = log_idx;
        while let Some(log) = self.logs.get(&cur_idx) {
            if log.ns() == ns {
                bdd = bdd.or(log.input_query().bdd()).unwrap();
            }
            cur_idx = log.get_prev_log_idx();
        }
        bdd
    }

    pub fn get_num_traces(&self) -> usize {
        self.traces.len()
    }

    pub fn trace_paths(&self, trace_indices: Option<&[usize]>) -> Vec<(usize, Vec<usize>)> {
        let indices: Vec<usize> = match trace_indices {
            Some(indices) => indices.to_vec(),
            None => (0..self.traces.len()).collect(),
        };
        indices
            .into_iter()
            .filter_map(|trace_idx| {
                let trace = self.traces.get(trace_idx)?;
                let mut path = Vec::new();
                let mut cur_log_idx = trace.end_log_idx;
                while let Some(log) = self.logs.get(&cur_log_idx) {
                    path.push(cur_log_idx);
                    let prev = log.get_prev_log_idx();
                    if prev == usize::MAX {
                        break;
                    }
                    cur_log_idx = prev;
                }
                path.reverse();
                Some((trace_idx, path))
            })
            .collect()
    }

    fn _property_checking_par(&self, lec_mgr: &LECManager, traces: &[&Trace]) -> HashSet<String> {
        let errors = traces
            .par_chunks(5000)
            .map(|traces| {
                let mut errors = HashSet::new();
                for trace in traces {
                    let mut hops = 0;
                    let mut rewrites = 0;
                    let mut refuse = false;
                    let mut nx_domain = false;
                    let mut prev_zone = ("", usize::MAX);
                    let mut len = 0;
                    let mut cur_log_idx = trace.end_log_idx;
                    while let Some(log) = self.logs.get(&cur_log_idx) {
                        len += 1;
                        match log.get_action() {
                            ActionType::RewriteC | ActionType::RewriteD => rewrites += 1,
                            ActionType::Refuse => refuse = true,
                            ActionType::NonExist => nx_domain = true,
                            _ => {}
                        }

                        let cur_zone = (log.ns().as_str(), log.get_zone_idx());
                        if cur_zone != prev_zone {
                            hops += 1;
                            prev_zone = cur_zone;
                        }

                        cur_log_idx = log.get_prev_log_idx();
                    }
                    if hops > 5 {
                        errors.insert("hops".to_string());
                    }
                    if rewrites > 2 {
                        errors.insert("rewrites".to_string());
                    }
                    if refuse && len > 2 {
                        errors.insert("lame delegation".to_string());
                    }
                    if rewrites > 0 && refuse && nx_domain {
                        errors.insert("rewrite blackholing".to_string());
                    }
                    if rewrites > 0 {
                        errors.insert(format!("rewrite {}", rewrites));
                    }
                    if len > 2 {
                        let cur_log = self.logs.get(&trace.end_log_idx).unwrap();
                        if cur_log.get_action() == ActionType::Answer {
                            let prev_log = self.logs.get(&cur_log.get_prev_log_idx()).unwrap();
                            if prev_log.get_action() == ActionType::Delegate {
                                let mut delegation_consistency = true;
                                let zonefile_bdd_parent = lec_mgr
                                    .get_zonefile_bdd_ref(prev_log.ns(), prev_log.zone_idx)
                                    .unwrap();
                                let zonefile_bdd_child = lec_mgr
                                    .get_zonefile_bdd_ref(cur_log.ns(), cur_log.zone_idx)
                                    .unwrap();
                                let record_parent = zonefile_bdd_parent
                                    .get_record_bdd_ref(prev_log.record_idx)
                                    .unwrap();
                                let record_child =
                                    zonefile_bdd_child.records().iter().find(|(_, record)| {
                                        record.get_rtype() == crate::record::RecordType::NS
                                            && record.name() == record_parent.name()
                                    });
                                if let Some((_, record_child)) = record_child {
                                    let mut rdata_set: HashSet<&String> =
                                        record_parent.rdata().iter().collect();
                                    for rdata in record_child.rdata() {
                                        if !rdata_set.contains(rdata) {
                                            delegation_consistency = false;
                                            break;
                                        }
                                        rdata_set.remove(rdata);
                                        let ip_parent = zonefile_bdd_parent.get_ip_ref(&rdata);
                                        let ip_child = zonefile_bdd_child.get_ip_ref(&rdata);
                                        if ip_parent != ip_child
                                            && Utils::is_subdomain(
                                                &Utils::string_to_domain(rdata, false),
                                                zonefile_bdd_child.origin(),
                                            )
                                        {
                                            delegation_consistency = false;
                                            break;
                                        }
                                    }
                                    if !rdata_set.is_empty() {
                                        delegation_consistency = false;
                                    }
                                } else {
                                    delegation_consistency = false;
                                }
                                if !delegation_consistency {
                                    errors.insert("delegation consistency".to_string());
                                }
                            }
                        }
                    }
                }
                errors
            })
            .reduce(
                || HashSet::new(),
                |mut acc, mut errors| {
                    acc.extend(errors.drain());
                    acc
                },
            );
        errors
    }

    pub fn property_checking_par(&self, lec_mgr: &LECManager) -> Vec<String> {
        let errors = self
            .traces
            .par_chunks(5000)
            .map(|traces| {
                let mut errors = Vec::new();
                for trace in traces {
                    let mut hops = 0;
                    let mut rewrites = 0;
                    let mut refuse = false;
                    let mut nx_domain = false;
                    let mut prev_zone = ("", usize::MAX);
                    let mut len = 0;
                    let mut cur_log_idx = trace.end_log_idx;
                    let is_loop = self.logs.get(&cur_log_idx).unwrap().action == ActionType::Loop;
                    while let Some(log) = self.logs.get(&cur_log_idx) {
                        len += 1;
                        match log.get_action() {
                            ActionType::RewriteC | ActionType::RewriteD => rewrites += 1,
                            ActionType::Refuse => refuse = true,
                            ActionType::NonExist => nx_domain = true,
                            _ => {}
                        }

                        let cur_zone = (log.ns().as_str(), log.get_zone_idx());
                        if cur_zone != prev_zone {
                            hops += 1;
                            prev_zone = cur_zone;
                        }

                        cur_log_idx = log.get_prev_log_idx();
                    }
                    if hops > 5 {
                        errors.push("hops".to_string());
                    }
                    if rewrites > 2 {
                        errors.push("rewrites".to_string());
                    }
                    if refuse && len > 2 {
                        errors.push("lame delegation".to_string());
                    }
                    if rewrites > 0 && refuse && nx_domain {
                        errors.push("rewrite blackholing".to_string());
                    }
                    if rewrites > 0 {
                        errors.push(format!("rewrite {}", rewrites));
                    }
                    if is_loop {
                        errors.push("loop".to_string());
                    }
                    if len > 2 {
                        let cur_log = self.logs.get(&trace.end_log_idx).unwrap();
                        if cur_log.get_action() == ActionType::Answer {
                            let prev_log = self.logs.get(&cur_log.get_prev_log_idx()).unwrap();
                            if prev_log.get_action() == ActionType::Delegate {
                                let mut delegation_consistency = true;
                                let zonefile_bdd_parent = lec_mgr
                                    .get_zonefile_bdd_ref(prev_log.ns(), prev_log.zone_idx)
                                    .unwrap();
                                let zonefile_bdd_child = lec_mgr
                                    .get_zonefile_bdd_ref(cur_log.ns(), cur_log.zone_idx)
                                    .unwrap();
                                let record_parent = zonefile_bdd_parent
                                    .get_record_bdd_ref(prev_log.record_idx)
                                    .unwrap();
                                let record_child =
                                    zonefile_bdd_child.records().iter().find(|(_, record)| {
                                        record.get_rtype() == crate::record::RecordType::NS
                                            && record.name() == record_parent.name()
                                    });
                                if let Some((_, record_child)) = record_child {
                                    let mut rdata_set: HashSet<&String> =
                                        record_parent.rdata().iter().collect();
                                    for rdata in record_child.rdata() {
                                        if !rdata_set.contains(rdata) {
                                            delegation_consistency = false;
                                            break;
                                        }
                                        rdata_set.remove(rdata);
                                        let ip_parent = zonefile_bdd_parent.get_ip_ref(&rdata);
                                        let ip_child = zonefile_bdd_child.get_ip_ref(&rdata);
                                        if ip_parent != ip_child
                                            && Utils::is_subdomain(
                                                &Utils::string_to_domain(rdata, false),
                                                zonefile_bdd_child.origin(),
                                            )
                                        {
                                            delegation_consistency = false;
                                            break;
                                        }
                                    }
                                    if !rdata_set.is_empty() {
                                        delegation_consistency = false;
                                    }
                                } else {
                                    delegation_consistency = false;
                                }
                                if !delegation_consistency {
                                    errors.push("delegation consistency".to_string());
                                }
                            }
                        }
                    }
                }
                errors
            })
            .reduce(
                || Vec::new(),
                |mut acc, mut errors| {
                    acc.append(&mut errors);
                    acc
                },
            );
        errors
    }

    pub fn inc_property_checking_par(
        &self,
        lec_mgr: &LECManager,
        idxs: Vec<usize>,
    ) -> HashSet<String> {
        self._property_checking_par(
            lec_mgr,
            &idxs
                .iter()
                .map(|idx| &self.traces[*idx])
                .collect::<Vec<_>>(),
        )
    }
}
