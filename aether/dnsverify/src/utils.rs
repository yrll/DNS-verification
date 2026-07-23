use crate::record::RecordType;
use rand::prelude::*;
use serde::Deserialize;

pub struct Utils;

const NOR_WILDCARD: &str = "\\*"; // rdata中的*只能是普通的label，不能是通配符

impl Utils {
    pub fn domain_to_string(domain: &Vec<String>) -> String {
        domain
            .iter()
            .rev()
            .map(|x| x.clone() + ".")
            .collect::<String>()
    }

    /** 将name的vector表示转为String表示，flag用来表示将*视为通配符（true）还是label（false） */
    pub fn string_to_domain(domain: &str, flag: bool) -> Vec<String> {
        domain
            .split(".")
            .filter(|x| !x.is_empty())
            .map(|x| {
                if !flag && x == "*" {
                    NOR_WILDCARD.to_string()
                } else {
                    x.to_string()
                }
            })
            .collect::<Vec<String>>()
            .into_iter()
            .rev()
            .collect()
    }

    pub fn is_subdomain(sub: &Vec<String>, parent: &Vec<String>) -> bool {
        if sub.len() < parent.len() {
            return false;
        }
        for i in 0..parent.len() {
            if sub[i] != parent[i] {
                return false;
            }
        }
        true
    }

    pub fn is_pre_match(name1: &Vec<String>, name2: &Vec<String>) -> bool {
        for (a, b) in name1.iter().zip(name2.iter()) {
            if a != b {
                return false;
            }
        }
        true
    }

    /** 为一个record计算优先级，负责转发的NS优先级为偶数，负责重写的DNAME优先级为奇数 */
    pub fn record_rank(domain: &Vec<String>, rtype: &RecordType, origin: &Vec<String>) -> usize {
        let is_cname = if *rtype == RecordType::CNAME { 1 } else { 0 };
        if domain.last().unwrap() == "*" {
            is_cname // 0 给普通记录，1 给CNAME
        } else if *rtype == RecordType::NS && domain != origin {
            512 - domain.len() * 2 // NS记录为大于3的偶数
        } else if *rtype == RecordType::DNAME {
            512 - domain.len() * 2 - 1 // DNAME记录为大于3的奇数
        } else {
            2 + is_cname // 2 给普通记录，3 给CNAME
        }
    }

    /** 随机生成一个又a-z组成的label */
    pub fn random_label(rng: &mut rand::rngs::ThreadRng, len: usize) -> String {
        let mut label = String::new();
        for _ in 0..len {
            label.push(rng.gen_range('a'..'z'));
        }
        label
    }
}

pub struct MetaParser;

#[derive(Debug, Deserialize)]
struct Config {
    #[serde(rename = "TopNameServers")]
    top_name_servers: Vec<String>,
    #[serde(rename = "ZoneFiles")]
    zone_files: Vec<ZoneFile>,
}

#[derive(Debug, Deserialize)]
struct ZoneFile {
    #[serde(rename = "FileName")]
    file_name: String,
    #[serde(rename = "NameServer")]
    name_server: String,
    #[serde(rename = "Origin")]
    origin: Option<String>,
}

impl MetaParser {
    pub fn parse_metadata(fpath: &str) -> (Vec<String>, Vec<(String, String, Vec<String>)>) {
        let file = std::fs::File::open(fpath).unwrap();
        let reader = std::io::BufReader::new(file);
        let config = match serde_json::from_reader(reader) {
            Ok(config) => config,
            Err(e) => {
                log::error!("Failed to parse metadata file: {}", e);
                Config {
                    top_name_servers: vec![],
                    zone_files: vec![],
                }
            }
        };
        let dir_str = std::path::Path::new(fpath)
            .parent()
            .unwrap()
            .to_str()
            .unwrap();
        let top_ns = config.top_name_servers;
        let zones = config
            .zone_files
            .into_iter()
            .map(|z| {
                let domain = match z.origin {
                    Some(origin) => origin
                        .trim_end_matches('.')
                        .split(".")
                        .map(|s| s.to_string())
                        .collect::<Vec<String>>(),
                    None => vec![],
                };
                let file_path = std::path::Path::new(&z.file_name);
                let fpath = if file_path.is_absolute() {
                    z.file_name
                } else {
                    format!("{}/{}", dir_str, z.file_name)
                };
                (fpath, z.name_server, domain.iter().rev().map(|s| s.to_string()).collect())
            })
            .collect::<Vec<(String, String, Vec<String>)>>();
        (top_ns, zones)
    }
}
