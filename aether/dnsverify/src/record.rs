use std::str::FromStr;

#[derive(
    Debug,
    Clone,
    Copy,
    PartialEq,
    Eq,
    PartialOrd,
    Ord,
    Hash,
    strum_macros::EnumString,
    strum_macros::EnumCount,
    strum_macros::EnumIter,
)]
pub enum RecordType {
    ALL, // for all types
    A,
    AAAA,
    CNAME,
    DNAME,
    MX,
    NS,
    PTR,
    SOA,
    SRV,
    TXT,
}

#[derive(Debug, Clone)]
pub struct Record {
    domain: Vec<String>,
    rtype: RecordType,
    rdata: String,
}

impl Record {
    pub fn new(domain: Vec<String>, rtype: String, rdata: String) -> Record {
        Record {
            domain,
            rtype: RecordType::from_str(rtype.as_str()).unwrap(),
            rdata,
        }
    }

    pub fn create(domain: Vec<String>, rtype: RecordType, rdata: String) -> Record {
        Record {
            domain,
            rtype,
            rdata,
        }
    }

    pub fn domain(&self) -> &Vec<String> {
        &self.domain
    }

    pub fn rtype(&self) -> RecordType {
        self.rtype.clone()
    }

    pub fn rdata(&self) -> &String {
        &self.rdata
    }

    pub fn into_tuple(self) -> (Vec<String>, RecordType, String) {
        (self.domain, self.rtype, self.rdata)
    }
}
