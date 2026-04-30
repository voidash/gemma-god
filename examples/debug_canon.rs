use gemma_god::crawler_v2::canonicalize;
fn main() {
    for url in [
        "http://127.0.0.1:65432/",
        "http://127.0.0.1:65432",
        "http://localhost:65432/",
    ] {
        let r = canonicalize(url, url);
        println!("{:?} => {:?}", url, r);
    }
}
