use oxidd::bdd::BDDFunction;

#[derive(Clone, PartialEq, Eq)]
pub struct Query {
    bdd: BDDFunction,
    prefix: Vec<String>,
}

#[allow(dead_code)]
impl Query {
    pub fn new(bdd: BDDFunction, prefix: Vec<String>) -> Query {
        Query { bdd, prefix }
    }

    pub fn bdd(&self) -> &BDDFunction {
        &self.bdd
    }

    pub fn prefix(&self) -> &Vec<String> {
        &self.prefix
    }

    pub fn get_prefix(&self) -> Vec<String> {
        self.prefix.clone()
    }
}
