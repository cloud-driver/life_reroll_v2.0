export function passwordLength(value:string){return Array.from(value).length;}
export function validPasswordLength(value:string){const n=passwordLength(value);return n>=12&&n<=128;}
export function passwordLengthHint(value:string){
 const n=passwordLength(value);
 if(!n)return '新密碼須為 12 至 128 字。';
 if(n<12)return `密碼至少需要 12 字，目前 ${n} 字，還差 ${12-n} 字。`;
 if(n>128)return `密碼最多 128 字，目前 ${n} 字。`;
 return '密碼長度符合規則。';
}
