/* RentMyRide shared frontend demo. Data stays in this browser (localStorage), not a secure production backend. */
(function(){
 const $=id=>document.getElementById(id), read=(k,d=[])=>{try{return JSON.parse(localStorage.getItem('rmr_'+k))??d}catch{return d}}, write=(k,v)=>localStorage.setItem('rmr_'+k,JSON.stringify(v));
 const path=location.pathname.split('/').pop();
 const adminPages=['admin-dashboard.html','admin-providers.html','admin-vehicles.html','admin-bookings.html','admin-reports.html','admin-customers.html','admin-complaints.html','admin-payments.html','admin-settings.html'];
 if(adminPages.includes(path)&&sessionStorage.getItem('adminLoggedIn')!=='true'){location.replace('admin-login.html');return;}
 if(path==='provider-dashboard.html'&&sessionStorage.getItem('providerLoggedIn')!=='true'){location.replace('login.html');return;}
 document.addEventListener('submit',function(e){const f=e.target;if(!(f instanceof HTMLFormElement))return;const id=f.id;
  if(['signupForm','passwordForm','otpForm','loginForm','forgotPasswordForm','adminLoginForm','providerForm','addVehicleForm'].includes(id)){e.preventDefault();e.stopImmediatePropagation();}
  const msg=$('message'); const say=(t,ok=false)=>{if(msg){msg.textContent=t;msg.style.color=ok?'#087f5b':'#c62828';}};
  if(id==='signupForm'){
   const c=$('contact')?.value.trim()||'', email=/^[\w.%+-]+@gmail\.com$/i.test(c), phone=/^[6-9]\d{9}$/.test(c); if(!email&&!phone)return say('Enter a valid Gmail address or Indian mobile number.');
   sessionStorage.setItem('rmr_signupContact',c);sessionStorage.setItem('rmr_signupType',email?'email':'phone');sessionStorage.removeItem('rmr_otpPurpose');location.href='otp.html';
  } else if(id==='otpForm'){
   const digits=[...document.querySelectorAll('.otp-digit')].map(x=>x.value).join('');if(!/^\d{6}$/.test(digits))return say('Enter all 6 OTP digits.');
   if(digits!=='123456')return say('Demo OTP is 123456. Enter the correct 6 digits.');
   sessionStorage.setItem('rmr_otpVerified','true');location.href='create_password.html';
  } else if(id==='passwordForm'){
   if(sessionStorage.getItem('rmr_otpVerified')!=='true')return say('Please verify OTP first.');
   const p=$('password')?.value||'', cp=$('confirmPassword')?.value||'';if(p.length!==8||!/[A-Z]/.test(p)||!/[a-z]/.test(p)||!/[0-9]/.test(p))return say('Password must be exactly 8 characters and include uppercase, lowercase and a number.');if(p!==cp)return say('Passwords do not match.');
   const contact=sessionStorage.getItem('rmr_signupContact')||'';let users=read('users',[]);if(users.some(u=>u.contact.toLowerCase()===contact.toLowerCase()))return say('This account already exists. Please log in.');users.push({contact,password:p,role:'customer',createdAt:new Date().toISOString()});write('users',users);sessionStorage.removeItem('rmr_otpVerified');sessionStorage.removeItem('rmr_signupContact');say('Account created. Redirecting to login...',true);setTimeout(()=>location.href='login.html',800);
  } else if(id==='loginForm'){
   const c=$('contact')?.value.trim()||$('email')?.value.trim()||'', p=$('password')?.value||'';const u=read('users',[]).find(x=>x.contact.toLowerCase()===c.toLowerCase()&&x.password===p);if(!u)return say('Account not found or password incorrect. Please sign up first.');sessionStorage.setItem('rmr_user',u.contact);sessionStorage.setItem('providerLoggedIn',u.role==='provider'?'true':'false');location.href=u.role==='provider'?'provider-dashboard.html':'vehicles.html';
  } else if(id==='forgotPasswordForm'){
   const c=$('contact')?.value.trim()||'';if(!read('users',[]).some(u=>u.contact.toLowerCase()===c.toLowerCase()))return say('Account not found. Please check your registered contact.');sessionStorage.setItem('rmr_signupContact',c);sessionStorage.setItem('rmr_otpPurpose','forgot');location.href='otp.html';
  } else if(id==='adminLoginForm'){
   const email=$('adminEmail')?.value.trim().toLowerCase(),pass=$('adminPassword')?.value;if(email!=='admin@rentmyride.com'||pass!=='Admin@123')return say('Invalid admin email or password.');sessionStorage.setItem('adminLoggedIn','true');location.href='admin-dashboard.html';
  } else if(id==='providerForm'){
   const data=Object.fromEntries(new FormData(f).entries());const phone=$('phone')?.value.trim()||'';if(!/^[6-9]\d{9}$/.test(phone))return say('Enter valid 10-digit Indian mobile number.');const providers=read('providers',[]);data.id='P'+Date.now();data.phone=phone;data.status='Pending';data.createdAt=new Date().toISOString();data.documentNames=[...f.querySelectorAll('input[type=file]')].flatMap(x=>[...x.files].map(z=>z.name));providers.push(data);write('providers',providers);say('Application saved in this browser as Pending. File contents are not uploaded; connect Firebase Storage for secure uploads.',true);
  } else if(id==='addVehicleForm'){
   const vehicles=read('vehicles',[]),data=Object.fromEntries(new FormData(f).entries());data.id='V'+Date.now();data.owner=sessionStorage.getItem('rmr_user')||'Demo Provider';data.status='Pending';data.createdAt=new Date().toISOString();data.photoNames=[...f.querySelectorAll('input[type=file]')].flatMap(x=>[...x.files].map(z=>z.name));vehicles.push(data);write('vehicles',vehicles);say('Vehicle saved locally and marked Pending for admin review.',true);f.reset();
  }
 },true);
 // Correct navigation and shared admin summaries
 document.querySelectorAll('a[href]').forEach(a=>{const h=a.getAttribute('href');const map={'admin-login.html':'admin-login.html','admin-dashboard.html':'admin-dashboard.html','admin-providers.html':'admin-providers.html','admin-vehicles.html':'admin-vehicles.html','admin-bookings.html':'admin-bookings.html','admin-reports.html':'admin-reports.html','provider-dashboard.html':'provider-dashboard.html'};if(map[h])a.href=map[h];});
 const providers=read('providers'),vehicles=read('vehicles'),bookings=read('bookings'),users=read('users');
 const set=(id,v)=>{if($(id))$(id).textContent=v;};
 set('totalProviders',providers.length);set('pendingProviders',providers.filter(x=>x.status==='Pending').length);set('approvedProviders',providers.filter(x=>x.status==='Approved').length);set('totalVehicles',vehicles.length);set('totalBookings',bookings.length);set('providers',providers.length);set('vehicles',vehicles.length);set('bookings',bookings.length);set('totalCustomers',users.filter(x=>x.role==='customer').length);set('total',providers.length);set('pending',providers.filter(x=>x.status==='Pending').length);set('approved',providers.filter(x=>x.status==='Approved').length);set('pendingVehicles',vehicles.filter(x=>x.status==='Pending').length);set('approvedVehicles',vehicles.filter(x=>x.status==='Approved').length);set('totalVehicles',vehicles.length);set('totalBookings',bookings.length);
 const list=$('providerList');if(list&&providers.length){list.innerHTML=providers.map(p=>`<article class="card"><h3>${esc(p.ownerName||p.name||'Provider')}</h3><p>${esc(p.phone||'')} · ${esc(p.location||p.address||'')}</p><p>Status: <b>${esc(p.status)}</b></p><button data-approve-provider="${p.id}">Approve</button> <button data-reject-provider="${p.id}">Reject</button></article>`).join('');}
 const vlist=$('vehicleList');if(vlist&&vehicles.length){vlist.innerHTML=vehicles.map(v=>`<article class="card"><h3>${esc(v.vehicleModel||v.model||v.vehicleType||'Vehicle')}</h3><p>${esc(v.registrationNumber||'')} · ₹${esc(v.rent||v.price||'')}/day</p><p>Status: <b>${esc(v.status)}</b></p><button data-approve-vehicle="${v.id}">Approve</button> <button data-reject-vehicle="${v.id}">Reject</button></article>`).join('');}
 document.addEventListener('click',e=>{let b=e.target.closest('button');if(!b)return;for(const [attr,key,status] of [['data-approve-provider','providers','Approved'],['data-reject-provider','providers','Rejected'],['data-approve-vehicle','vehicles','Approved'],['data-reject-vehicle','vehicles','Rejected']])if(b.hasAttribute(attr)){let a=read(key);a=a.map(x=>x.id===b.getAttribute(attr)?{...x,status}:x);write(key,a);location.reload();}});
 function esc(s){return String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
})();
