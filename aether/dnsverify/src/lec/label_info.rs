use std::collections::HashMap;
use std::sync::{Arc, RwLock};

pub struct LabelInfo {
    start: usize,
    num_bit: usize,
    words_table: Arc<RwLock<HashMap<String, usize>>>,
}

impl LabelInfo {
    pub fn new(
        start: usize,
        num_bit: usize,
        words_table: Arc<RwLock<HashMap<String, usize>>>,
    ) -> Self {
        LabelInfo {
            start,
            num_bit,
            words_table,
        }
    }

    pub fn words_table(&self) -> &Arc<RwLock<HashMap<String, usize>>> {
        &self.words_table
    }

    pub fn get_words_table(&self) -> Arc<RwLock<HashMap<String, usize>>> {
        self.words_table.clone()
    }

    pub fn get_num_bit(&self) -> usize {
        self.num_bit
    }

    pub fn get_start(&self) -> usize {
        self.start
    }

    pub fn get_end(&self) -> usize {
        self.start + self.num_bit
    }

    pub fn add_word(&mut self, word: &str) {
        let mut table = self.words_table.write().unwrap();
        if table.contains_key(word) {
            return;
        }
        let val = table.len();
        table.insert(word.to_string(), val);
    }
}
