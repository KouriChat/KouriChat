var d = new ActiveXObject("TestDispServerLib.TestDispServer");

//WScript.Echo("d.Name");
if (d.Name != "spam, spam, spam")
  throw new Error(d.Name);

//WScript.Echo("d.Name = 'foo'");
d.Name = "foo";

//WScript.Echo("d.Name");
if (d.Name != "foo")
  throw new Error(d.Name);

//WScript.Echo("d.Eval('1 + 2')");
var result = d.Eval("1 + 2");
if (result != 3)
  throw new Error(result);
