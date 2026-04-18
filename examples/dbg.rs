use gemma_god::convert_mixed;

fn main() {
    let input = "नेपाल सरकार Government of Nepal";
    let out = convert_mixed(input, "Preeti");
    eprintln!("INPUT:  {:?}", input);
    eprintln!("OUTPUT: {:?}", out);
    eprintln!("contains नेपाल: {}", out.contains("नेपाल"));
    eprintln!("contains सरकार: {}", out.contains("सरकार"));
    eprintln!("contains Government: {}", out.contains("Government"));
    
    let input2 = "Nepal Standard Industrial Classification lqmofsnfksf gfd tyf ljj/0f";
    let out2 = convert_mixed(input2, "Preeti");
    eprintln!("\nINPUT:  {:?}", input2);
    eprintln!("OUTPUT: {:?}", out2);
}
