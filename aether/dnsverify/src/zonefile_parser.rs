use super::record::{Record, RecordType};
use pest::error::Error as PestError;
use pest::iterators::Pair;
use pest::Parser;
use pest_derive::Parser;
use std::{collections::HashSet, fmt, fs, io, path::Path};

#[derive(Parser)]
#[grammar_inline = r#"
WHITESPACE      =   _{ " " | "\t" }
COMMENT         =   _{ ";" ~ (!NEWLINE ~ ANY)* }
SPACE           =   _{ " " | "\t" }

// escaped_quote   =   { "\\\"" }
// 为了兼容census里类似 "allemaal!\""" 的情况
escaped_quote   =   { ("\\\"" ~ &"\"\"" ~ "\"") | "\\\"" }
escaped_paren   =   { "\\(" | "\\)" }
non_quote       =   { !("\"" | NEWLINE) ~ ANY }
non_paren       =   { !("(" | ")"  | NEWLINE | SPACE | "\"" | ";") ~ ANY }
string          =   { "\"" ~ (escaped_quote | non_quote)* ~ "\"" }

base            =    @{ string | (escaped_paren | non_paren)+ } 
parens          =    { "(" ~ (base | parens | NEWLINE)* ~ ")" }
expression      =    { (parens | base)+ }

file            =   _{ SOI ~ NEWLINE* ~ (expression ~ NEWLINE+)* ~ EOI }

dfname          =   @{ "." | ".." | (!("/" | "\\" | "(" | ")" | "\"") ~ ANY)+ }
linuxpath       =   @{ "/"? ~ (dfname ~ "/")* ~ dfname }
winpath         =   @{ (ASCII_ALPHA_UPPER ~ ":" ~ "\\")? ~ (dfname ~ "\\")* ~ dfname }
lwpath          =   @{ linuxpath | winpath }
path            =   ${ "\"" ~ lwpath ~ "\"" | lwpath }

label           =   @{ (ASCII_ALPHANUMERIC+ ~ ("-"+ ~ ASCII_ALPHANUMERIC+)*) | "*" }
domain          =   ${ label ~ ("." ~ label)* ~ "."? }

time            =   @{ ASCII_DIGIT+ ~ (^"w" | ^"d" | ^"h" | ^"m" | ^"s")? }
name            =   @{ "@" | domain }
class           =   @{ "IN" | "CH" | "HS" }
rtype           =   @{ "AAAA" | "A" | "CNAME" | "MX" | "NS" | "SOA" | "PTR" | "TXT" | "DNAME" }
value           =   @{ (!(NEWLINE) ~ ANY)+ }

origin          =   ${ ^"$ORIGIN" ~ SPACE+ ~ domain }
ttl             =   ${ ^"$TTL" ~ SPACE+ ~ time }
include         =   ${ ^"$INCLUDE" ~ SPACE+ ~ path }

record1         =   ${ (name ~ SPACE+)? ~ (time ~ SPACE+)? ~ (class ~ SPACE+)? ~ rtype ~ SPACE+ ~ value? }
record2         =   ${ (name ~ SPACE+)? ~ (class ~ SPACE+)? ~ (time ~ SPACE+)? ~ rtype ~ SPACE+ ~ value? }
record3         =   ${ (name ~ SPACE+)? ~ (time ~ SPACE+)? ~ rtype ~ SPACE+ ~ (class ~ SPACE+)? ~ value? }
record4         =   ${ (name ~ SPACE+)? ~ (class ~ SPACE+)? ~ rtype ~ SPACE+ ~ (time ~ SPACE+)? ~ value? }
record5         =   ${ (name ~ SPACE+)? ~ rtype ~ SPACE+ ~ (time ~ SPACE+)? ~ (class ~ SPACE+)? ~ value? }
record6         =   ${ (name ~ SPACE+)? ~ rtype ~ SPACE+ ~ (class ~ SPACE+)? ~ (time ~ SPACE+)? ~ value? }
record          =   ${ record1 | record2 | record3 | record4 | record5 | record6 }

line            =   _{ SOI ~ (origin | ttl | include | record) ~ EOI }

"#]
struct ZonefileParser;

#[derive(Debug)]
pub enum ParserError {
    IoError(io::Error),
    PestError(PestError<Rule>),
    LogicError(String),
}

impl fmt::Display for ParserError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            ParserError::IoError(e) => write!(f, "IO error: {}", e),
            ParserError::PestError(e) => write!(f, "Pest error: {}", e),
            ParserError::LogicError(e) => write!(f, "Logic error: {}", e),
        }
    }
}

impl From<io::Error> for ParserError {
    fn from(err: io::Error) -> Self {
        ParserError::IoError(err)
    }
}

impl From<PestError<Rule>> for ParserError {
    fn from(err: PestError<Rule>) -> Self {
        ParserError::PestError(err)
    }
}

impl From<String> for ParserError {
    fn from(err: String) -> Self {
        ParserError::LogicError(err)
    }
}

fn flatten_parens(pair: Pair<Rule>) -> String {
    let mut s = String::new();
    for inner_pair in pair.into_inner() {
        match inner_pair.as_rule() {
            Rule::base => {
                s.push_str(inner_pair.as_str());
                s.push_str(" ");
            }
            Rule::parens => {
                s.push_str(&flatten_parens(inner_pair));
            }
            _ => unreachable!(),
        }
    }
    s
}

fn get_line(pair: Pair<Rule>) -> String {
    let mut s = String::new();
    for inner_pair in pair.into_inner() {
        match inner_pair.as_rule() {
            Rule::base => {
                s.push_str(inner_pair.as_str());
                s.push_str(" ");
            }
            Rule::parens => {
                s.push_str(&flatten_parens(inner_pair));
            }
            _ => unreachable!(),
        }
    }
    s
}

fn pre_process(fpath: &str) -> Result<Vec<String>, ParserError> {
    let contents = fs::read_to_string(fpath)?;
    let pairs = ZonefileParser::parse(Rule::file, &contents)?;
    let mut lines = Vec::new();
    for pair in pairs {
        if pair.as_rule() == Rule::expression {
            // println!("Expression: {:?}", pair);
            lines.push(get_line(pair));
        }
    }
    Ok(lines)
}

fn parse_recur(
    fpath: &str,
    domain: &mut Vec<String>,
    records: &mut Vec<Record>,
) -> Result<Option<Vec<String>>, ParserError> {
    let filepath = Path::new(fpath);
    let dir = filepath.parent().unwrap();

    let contents = pre_process(fpath)?;
    let mut dname = &domain.clone();
    let mut tmp; // Only for processing the include directive
    let mut soa_domain = None;
    for line in contents {
        let pair = ZonefileParser::parse(Rule::line, &line)?.next().unwrap();
        match pair.as_rule() {
            Rule::origin => {
                let domain_pair = pair.into_inner().next().unwrap();
                domain.clear();
                for label in domain_pair.into_inner().rev() {
                    domain.push(label.as_str().to_string());
                }
            }
            Rule::ttl => {}
            Rule::include => {
                let lwpath = pair
                    .into_inner()
                    .next()
                    .unwrap()
                    .into_inner()
                    .next()
                    .unwrap()
                    .as_str();
                let temp_path = dir.join(lwpath);
                let abs_path = if Path::new(lwpath).is_absolute() {
                    lwpath
                } else {
                    temp_path.to_str().unwrap()
                };
                tmp = dname.clone();
                dname = &tmp;
                let soa_d = parse_recur(abs_path, &mut dname.clone(), records)?;
                if soa_d.is_some() {
                    soa_domain = soa_d;
                }
            }
            Rule::record => {
                let pair = pair.into_inner().next().unwrap();
                let mut name_pair = None;
                let mut rtype = None;
                let mut rdata = None;
                for inner_pair in pair.into_inner() {
                    match inner_pair.as_rule() {
                        Rule::name => name_pair = Some(inner_pair),
                        Rule::rtype => rtype = Some(inner_pair.as_str().to_string()),
                        Rule::value => rdata = Some(inner_pair.as_str().to_string()),
                        _ => (),
                    }
                }
                let name_pair = name_pair.unwrap();
                let name = name_pair.as_str();
                let domain = if name == "" || name == "@" {
                    if dname.is_empty() {
                        return Err(ParserError::LogicError(
                            "No default domain name".to_string(),
                        ));
                    }
                    // dname.clone()
                    if name == "" {
                        dname.clone()
                    } else {
                        domain.clone()
                    }
                } else if name.ends_with(".") {
                    let domain_pair = name_pair.into_inner().next().unwrap();
                    let domain_ = domain_pair
                        .into_inner()
                        .rev()
                        .map(|x| x.as_str().to_string())
                        .collect::<Vec<String>>();
                    if rtype.as_ref().unwrap() == "SOA" {
                        domain.clear();
                        for label in domain_.iter() {
                            domain.push(label.clone());
                        }
                        soa_domain = Some(domain.clone());
                    }
                    domain_
                } else {
                    let mut domain = domain.clone();
                    name_pair
                        .into_inner()
                        .for_each(|x| domain.push(x.as_str().to_string()));
                    domain
                };
                let record = Record::new(
                    domain,
                    rtype.unwrap(),
                    rdata.unwrap_or_default().trim().to_string(),
                );
                records.push(record);
                dname = records.last().unwrap().domain();
            }
            Rule::EOI => (),
            _ => unreachable!(),
        }
    }
    Ok(soa_domain)
}

pub fn parse(fpath: &str, domain: &mut Vec<String>) -> Result<Vec<Record>, ParserError> {
    let mut records = Vec::new();
    let mut domain_ = domain.clone();
    log::debug!("Parsing zone file: {}", fpath);

    let soa_domain = parse_recur(fpath, &mut domain_, &mut records)?;
    if soa_domain.is_some() && domain.is_empty() {
        for label in soa_domain.unwrap() {
            domain.push(label);
        }
    }

    if !static_detect(&records) {
        return Err(ParserError::LogicError("Static error detected".to_string()));
    }

    return Ok(records);
}

fn static_detect(records: &Vec<Record>) -> bool {
    let mut cname_records = HashSet::new();
    for record in records {
        if record.rtype() == RecordType::DNAME && dname_loop(record) {
            log::error!("Static loop detected in DNAME record: {:?}", record);
            return false;
        }
        if wildcard_dname(record) {
            log::error!("Wildcard DNAME record detected: {:?}", record);
            return false;
        }
        if record.rtype() == RecordType::CNAME {
            if cname_records.contains(record.domain()) {
                log::error!("Duplicate CNAME record detected: {:?}", record);
                return false;
            }
            cname_records.insert(record.domain());
        }
    }
    for record in records {
        if record.rtype() != RecordType::CNAME && cname_records.contains(record.domain()) {
            log::error!(
                "CNAME record could not coexist with other records: {:?}",
                record
            );
            return false;
        }
    }
    true
}

fn dname_loop(record: &Record) -> bool {
    if record.rtype() != RecordType::DNAME {
        return false;
    }
    let domain = record
        .domain()
        .iter()
        .rev()
        .map(|label| label.to_string() + ".")
        .collect::<String>();
    let rdata = record.rdata();
    let domain_dot = ".".to_string() + &domain;
    let rdata_dot = ".".to_string() + rdata;
    rdata.ends_with(&domain_dot) || domain.ends_with(&rdata_dot) || *rdata == domain
}

fn wildcard_dname(record: &Record) -> bool {
    if record.rtype() != RecordType::DNAME {
        return false;
    }
    record.domain()[0] == "*"
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse() {
        let fpath = "/home/yaowang/dns/dnsv/resources/test.com..txt";
        let mut domain = vec![];
        let records = parse(fpath, &mut domain).unwrap();
        println!("ORIGIN: {:?}", domain);
        for record in records {
            println!("{:?}", record);
        }
    }
}
