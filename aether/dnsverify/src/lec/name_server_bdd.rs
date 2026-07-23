use super::{
    action::ActionType,
    query::Query,
    trace_log::{self, TraceLogManager},
    LECManager, ZoneFileBDD,
};
use super::{Domain, FPath, Records};
use oxidd::{bdd::BDDFunction, BooleanFunction};
use rayon::prelude::*;
use std::collections::HashMap;

pub struct NameServerBDD {
    ns: String,
    bdd: BDDFunction,
    zone_idx: usize,
    zones: HashMap<usize, ZoneFileBDD>,
}

#[allow(dead_code)]
impl NameServerBDD {
    pub fn bdd(&self) -> &BDDFunction {
        &self.bdd
    }

    pub fn get_idx(&self) -> usize {
        self.zone_idx
    }

    pub fn zones(&self) -> &HashMap<usize, ZoneFileBDD> {
        &self.zones
    }

    pub fn get_zonefile_bdd_ref(&self, zid: usize) -> Option<&ZoneFileBDD> {
        self.zones.get(&zid)
    }

    pub fn get_zonefile_bdd_mut(&mut self, zid: usize) -> Option<&mut ZoneFileBDD> {
        self.zones.get_mut(&zid)
    }
}

impl NameServerBDD {
    pub fn build_lec(
        lec_mgr: &LECManager,
        ns: String,
        zones: Vec<(FPath, Domain, Records)>,
    ) -> Self {
        // ns_bdd 是改ns下所有zone的并集（和）
        let mut ns_bdd = lec_mgr.bdd_f.clone();
        // let mut ns_zones = Vec::with_capacity(zones.len());
        let mut zone_idx = 0;
        let mut ns_zones = HashMap::with_capacity(zones.len());
        // Sort zones by the number of records (zone rank) in descending order (higher rank first) 已经在read_zonefiles中排序
        // zones.sort_by(|a, b| b.1.len().cmp(&a.1.len()));
        // zone_remain代表改ns剩下zone可用的bdd空间
        let mut zone_remain = lec_mgr.bdd_t.clone();
        for (fpath, origin, records) in zones {
            let zonefile_bdd = ZoneFileBDD::build_lec(
                lec_mgr,
                ns.clone(),
                zone_idx,
                fpath,
                origin,
                records,
                &zone_remain,
            );
            let union_start = lec_mgr.profile_start();
            zone_remain = zone_remain.and(&zonefile_bdd.bdd().not().unwrap()).unwrap();
            ns_bdd = ns_bdd.or(&zonefile_bdd.bdd()).unwrap();
            lec_mgr.profile_zone_ns_union(union_start);
            ns_zones.insert(zone_idx, zonefile_bdd);
            zone_idx += 1;
        }
        NameServerBDD {
            ns,
            bdd: ns_bdd,
            zone_idx,
            zones: ns_zones,
        }
    }

    pub fn process_query(
        &self,
        prev_log_idx: usize,
        query: Query,
        lec_mgr: &LECManager,
        tl_mgr: &TraceLogManager,
    ) -> Vec<(bool, trace_log::Log)> {
        // 需要处理的remain_bdd，即ns_bdd和query的交集，又可以说等待分割的空间
        let remain_bdd = self.bdd.and(query.bdd()).unwrap();
        // 不需要处理的query_bdd，即query减去ns_bdd
        let refuse_bdd = query.bdd().and(&self.bdd.not().unwrap()).unwrap();
        let depth = tl_mgr.get_log_depth(prev_log_idx).unwrap() + 1;
        let mut logs = Vec::new();
        if refuse_bdd != *lec_mgr.bdd_f() {
            logs.push((
                true,
                trace_log::Log::new(
                    0,
                    Query::new(refuse_bdd, query.get_prefix()),
                    None,
                    ActionType::Refuse,
                    self.ns.clone(),
                    None,
                    None,
                    None,
                    Some(prev_log_idx),
                    depth,
                ),
            ));
        }
        // 交集为空，直接返回
        if remain_bdd == *lec_mgr.bdd_f() {
            return logs;
        }
        // 检测是否有循环
        let dup_bdd = tl_mgr.get_dup_bdd(prev_log_idx, &self.ns, lec_mgr.bdd_f());
        let loop_bdd = remain_bdd.and(&dup_bdd).unwrap();
        let remain_bdd = remain_bdd.and(&dup_bdd.not().unwrap()).unwrap();
        // 有循环，记录循环日志
        if loop_bdd != *lec_mgr.bdd_f() {
            logs.push((
                true,
                trace_log::Log::new(
                    0,
                    Query::new(loop_bdd, query.get_prefix()),
                    None,
                    ActionType::Loop,
                    self.ns.clone(),
                    None,
                    None,
                    None,
                    Some(prev_log_idx),
                    depth,
                ),
            ));
        }
        // 与各个zonefile_bdd做交集，分割空间，获取对应的action
        for (_, zone) in self.zones() {
            let zone_bdd = zone.bdd();
            let match_bdd = remain_bdd.and(zone_bdd).unwrap();
            if match_bdd == *lec_mgr.bdd_f() {
                // 不与当前zonefile_bdd有交集
                continue;
            }

            let remain_bdd = match_bdd.and(&dup_bdd.not().unwrap()).unwrap();
            // 交由zonefile_bdd处理
            let zone_logs = zone.process_query(
                prev_log_idx,
                Query::new(remain_bdd, query.get_prefix()),
                lec_mgr,
                tl_mgr,
            );

            logs.extend(zone_logs);
        }
        logs
    }
}

/** 并行符号化执行代码 */
impl NameServerBDD {
    pub fn process_query_par(
        &self,
        prev_log_idx: usize,
        query: Query,
        lec_mgr: &LECManager,
        tl_mgr: &TraceLogManager,
    ) -> Vec<(bool, trace_log::Log)> {
        let remain_bdd = self.bdd.and(query.bdd()).unwrap();
        let refuse_bdd = query.bdd().and(&self.bdd.not().unwrap()).unwrap();
        let depth = tl_mgr.get_log_depth(prev_log_idx).unwrap() + 1;
        let mut logs = Vec::new();
        if refuse_bdd != *lec_mgr.bdd_f() {
            logs.push((
                true,
                trace_log::Log::new(
                    0,
                    Query::new(refuse_bdd, query.get_prefix()),
                    None,
                    ActionType::Refuse,
                    self.ns.clone(),
                    None,
                    None,
                    None,
                    Some(prev_log_idx),
                    depth,
                ),
            ));
        }
        if remain_bdd == *lec_mgr.bdd_f() {
            return logs;
        }
        let dup_bdd = tl_mgr.get_dup_bdd(prev_log_idx, &self.ns, lec_mgr.bdd_f());
        let loop_bdd = remain_bdd.and(&dup_bdd).unwrap();
        let remain_bdd = remain_bdd.and(&dup_bdd.not().unwrap()).unwrap();
        if loop_bdd != *lec_mgr.bdd_f() {
            logs.push((
                true,
                trace_log::Log::new(
                    0,
                    Query::new(loop_bdd, query.get_prefix()),
                    None,
                    ActionType::Loop,
                    self.ns.clone(),
                    None,
                    None,
                    None,
                    Some(prev_log_idx),
                    depth,
                ),
            ));
        }
        logs.par_extend(
            self.zones()
                .into_par_iter()
                .filter_map(|(_, zone)| {
                    let zone_bdd = zone.bdd();
                    let match_bdd = remain_bdd.and(zone_bdd).unwrap();
                    if match_bdd == *lec_mgr.bdd_f() {
                        return None;
                    }
                    let prefix = if zone.origin().len() > query.prefix().len() {
                        zone.origin().clone()
                    } else {
                        query.get_prefix()
                    };
                    let logs = zone.process_query_par(
                        prev_log_idx,
                        Query::new(match_bdd, prefix),
                        lec_mgr,
                        tl_mgr,
                    );

                    Some(logs)
                })
                .flatten(),
        );
        logs
    }
}
