use super::{
    action::{ActionCache, ActionType},
    WILDCARD,
};
use crate::record::RecordType;
use oxidd::{bdd::BDDFunction, BooleanFunction};
use std::collections::HashSet;

#[derive(Clone)]
pub struct RecordBDD {
    name: Vec<String>,
    rtype: RecordType,
    rank: usize,
    rdata: HashSet<String>,
    action: ActionType,
    action_cache: ActionCache, // 用来辅助CNAME和DNAME的重写
    hit: Option<BDDFunction>,
    bdd: BDDFunction,
}

/** constructor, getter, setter allow dead code */
#[allow(dead_code)]
impl RecordBDD {
    pub fn new(
        name: Vec<String>,
        rtype: RecordType,
        rank: usize,
        rdata: HashSet<String>,
        action: ActionType,
        action_cache: ActionCache,
        hit: Option<BDDFunction>,
        bdd: BDDFunction,
    ) -> Self {
        RecordBDD {
            name,
            rtype,
            rank,
            rdata,
            action,
            action_cache,
            hit,
            bdd,
        }
    }

    pub fn name(&self) -> &Vec<String> {
        self.name.as_ref()
    }

    pub fn get_name(&self) -> Vec<String> {
        self.name.clone()
    }

    pub fn get_concrete_name(&self) -> Vec<String> {
        self.name
            .iter()
            .filter(|&x| x != WILDCARD)
            .cloned()
            .collect()
    }

    pub fn get_rtype(&self) -> RecordType {
        self.rtype
    }

    pub fn get_rank(&self) -> usize {
        self.rank
    }

    pub fn rdata(&self) -> &HashSet<String> {
        &self.rdata
    }

    pub fn get_rdata(&self) -> HashSet<String> {
        self.rdata.clone()
    }

    pub fn get_action(&self) -> ActionType {
        self.action
    }

    pub fn action_cache(&self) -> &ActionCache {
        &self.action_cache
    }

    pub fn hit(&self) -> Option<&BDDFunction> {
        self.hit.as_ref()
    }

    pub fn bdd(&self) -> &BDDFunction {
        &self.bdd
    }

    pub fn add_rdata(&mut self, rdata: String) {
        self.rdata.insert(rdata);
    }

    pub fn del_bdd(&mut self, bdd: &BDDFunction) {
        self.bdd = self.bdd.and(&bdd.not().unwrap()).unwrap();
    }

    pub fn del_rdata(&mut self, rdata: &str) {
        self.rdata.remove(rdata);
    }

    pub fn add_bdd(&mut self, bdd: &BDDFunction) -> BDDFunction {
        let hit = self
            .hit
            .as_ref()
            .expect("record hit BDD is unavailable in full-only mode");
        let available = hit.and(&bdd).unwrap();
        self.bdd = self.bdd.or(&available).unwrap();
        bdd.and(&available.not().unwrap()).unwrap()
    }
}
