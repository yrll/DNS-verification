use oxidd::{bdd::BDDFunction, Subst};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ActionType {
    Answer,   // 直接返回答案
    RewriteD, // 由于DNAME导致的重写
    RewriteC, // 由于CNAME导致的重写
    Delegate, // 由于NS导致的委托
    Refuse,   // 由于拒绝服务，即该域名不属于本服务器管理范围
    NonExist, // 由于不存在，即该域名不存在
    Loop,     // 检测到循环
}

#[derive(Clone)]
pub enum ActionCache {
    // 保存rdata对应的BDD
    CNAME(BDDFunction),
    DNAME {
        substitution: Subst<BDDFunction, Vec<BDDFunction>>,
        target_bdd: BDDFunction,
        source_boundary: usize,
        valid_input_bdd: BDDFunction,
        output_padding_bdd: BDDFunction,
    },
    // other
    None,
}

impl ActionCache {
    /** 获取cache中存的rdata BDD，使用时必须保证self为CNAME/DNAME的cache */
    pub fn get_rdata_bdd(&self) -> &BDDFunction {
        match self {
            ActionCache::CNAME(bdd) => &bdd,
            ActionCache::DNAME { target_bdd, .. } => target_bdd,
            ActionCache::None => panic!("ActionCache::None has no rdata bdd"),
        }
    }

    /** 获取DNAME对应的所有Cache信息, 使用时必须保证self为DNAME */
    pub fn to_dname_cache(
        &self,
    ) -> (
        &Subst<BDDFunction, Vec<BDDFunction>>,
        &BDDFunction,
        usize,
        &BDDFunction,
        &BDDFunction,
    ) {
        match self {
            ActionCache::DNAME {
                substitution,
                target_bdd,
                source_boundary,
                valid_input_bdd,
                output_padding_bdd,
            } => (
                substitution,
                target_bdd,
                *source_boundary,
                valid_input_bdd,
                output_padding_bdd,
            ),
            _ => panic!("ActionCache::None or ActionCache::CNAME has no DNAME cache"),
        }
    }
}
