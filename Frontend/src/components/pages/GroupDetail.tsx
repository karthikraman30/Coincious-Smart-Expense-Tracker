import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../ui/card';
import { Button } from '../ui/button';
import { Badge } from '../ui/badge';
import { Avatar, AvatarFallback, AvatarImage } from '../ui/avatar';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../ui/tabs';
import { Separator } from '../ui/separator';
import { 
  ArrowLeft,
  Plus, 
  Users, 
  DollarSign, 
  Calendar,
  MoreVertical,
  Settings,
  UserPlus,
  Receipt,
  TrendingUp,
  Clock,
  Loader2
} from 'lucide-react';
import { Link, useParams } from 'react-router-dom';
import { supabase } from '../../utils/supabase/client';
import { toast } from 'sonner';
import { AddMemberDialog } from '../AddMemberDialog';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '../ui/dropdown-menu';

interface Member {
  id: string;
  email: string;
  name: string;
  avatar?: string;
  balance: number;
}

interface GroupData {
  id: string;
  name: string;
  description: string;
  members: Member[];
  totalExpenses: number;
  createdAt: string;
  lastActivity: string;
}

const expenses: any[] = [];
const settlements: any[] = [];

export function GroupDetail() {
  const { id } = useParams();
  const [activeTab, setActiveTab] = useState('expenses');
  const [groupData, setGroupData] = useState<GroupData>({
    id: id || '',
    name: 'Loading...',
    description: '',
    members: [],
    totalExpenses: 0,
    createdAt: new Date().toISOString().split('T')[0],
    lastActivity: 'Just now'
  });
  const [loading, setLoading] = useState(true);
  const [isAddMemberDialogOpen, setIsAddMemberDialogOpen] = useState(false);

  const [error, setError] = useState<Error | null>(null);

  const fetchGroupData = async () => {
    if (!id) return;
    
    try {
      setLoading(true);
      setError(null);
      
      const { data: { session } } = await supabase.auth.getSession();
      if (!session?.access_token) {
        throw new Error('No active session');
      }

      // Make parallel requests for better performance
      const [groupResponse, membersResponse] = await Promise.all([
        fetch(`http://localhost:8000/api/groups/${id}`, {
          headers: {
            'Authorization': `Bearer ${session.access_token}`,
            'Content-Type': 'application/json',
          },
        }),
        fetch(`http://localhost:8000/api/groups/${id}/members`, {
          headers: {
            'Authorization': `Bearer ${session.access_token}`,
            'Content-Type': 'application/json',
          },
        })
      ]);

      // Check both responses for errors
      if (!groupResponse.ok || !membersResponse.ok) {
        const errorData = await groupResponse.json().catch(() => ({}));
        throw new Error(errorData.error || 'Failed to fetch group data');
      }

      const [groupData, membersData] = await Promise.all([
        groupResponse.json(),
        membersResponse.json()
      ]);
      
      setGroupData({
        ...groupData.group,
        members: membersData.members || [],
      });
    } catch (error) {
      console.error('Error fetching group data:', error);
      const errorMessage = error instanceof Error ? error.message : 'Failed to load group data';
      setError(new Error(errorMessage));
      toast.error(errorMessage);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    // Only fetch if there's no error
    if (!error) {
      fetchGroupData();
    }
  }, [id, error]);

  const handleMemberAdded = () => {
    fetchGroupData(); // Refresh the group data to show the new member
  };

  const getCategoryIcon = (category: string) => {
    switch (category) {
      case 'Food & Dining': return '🍽️';
      case 'Transportation': return '🚗';
      case 'Accommodation': return '🏠';
      case 'Entertainment': return '🎉';
      default: return '💳';
    }
  };

  const getBalanceColor = (balance: number) => {
    if (balance > 0) return 'text-green-600';
    if (balance < 0) return 'text-red-600';
    return 'text-muted-foreground';
  };

  const getBalanceText = (balance: number) => {
    if (balance > 0) return `+$${balance.toFixed(2)}`;
    if (balance < 0) return `-$${Math.abs(balance).toFixed(2)}`;
    return '$0.00';
  };

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-[60vh] p-4">
        <div className="text-center space-y-4 max-w-md">
          <div className="bg-red-50 text-red-600 p-4 rounded-lg">
            <h3 className="font-medium">Failed to load group data</h3>
            <p className="text-sm mt-1">{error.message}</p>
          </div>
          <div className="flex gap-2 justify-center">
            <Button 
              variant="outline" 
              onClick={() => {
                setError(null);
                fetchGroupData();
              }}
            >
              <RefreshCw className="h-4 w-4 mr-2" />
              Retry
            </Button>
            <Button 
              variant="ghost" 
              asChild
            >
              <Link to="/groups">
                <ArrowLeft className="h-4 w-4 mr-2" />
                Back to Groups
              </Link>
            </Button>
          </div>
        </div>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-[60vh]">
        <div className="flex flex-col items-center gap-4">
          <Loader2 className="h-8 w-8 animate-spin text-primary" />
          <p className="text-muted-foreground">Loading group data...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="p-4 md:p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center gap-4">
        <Button variant="ghost" size="icon" asChild>
          <Link to="/groups">
            <ArrowLeft className="h-4 w-4" />
          </Link>
        </Button>
        <div className="flex-1">
          <h1 className="text-2xl md:text-3xl font-bold">{groupData.name}</h1>
        </div>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon">
              <MoreVertical className="h-4 w-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuLabel>Group Actions</DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem>
              <Settings className="h-4 w-4 mr-2" />
              Group Settings
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => setIsAddMemberDialogOpen(true)}>
              <UserPlus className="h-4 w-4 mr-2" />
              Add Members
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total Expenses</CardTitle>
            <DollarSign className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">${groupData.totalExpenses.toFixed(2)}</div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Members</CardTitle>
            <Users className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{groupData.members.length}</div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Expenses</CardTitle>
            <Receipt className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{expenses.length}</div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Last Activity</CardTitle>
            <Clock className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-sm font-medium">{groupData.lastActivity}</div>
          </CardContent>
        </Card>
      </div>

      {/* Add Expense Button */}
      <div className="flex justify-center md:justify-start">
        <Button size="lg" asChild>
          <Link to={`/add-expense?group=${id}`}>
            <Plus className="h-4 w-4 mr-2" />
            Add Expense
          </Link>
        </Button>
      </div>

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="grid w-full grid-cols-3">
          <TabsTrigger value="expenses">Expenses</TabsTrigger>
          <TabsTrigger value="balances">Balances</TabsTrigger>
          <TabsTrigger value="members">Members</TabsTrigger>
        </TabsList>

        <TabsContent value="expenses" className="space-y-4">
          {expenses.length === 0 ? (
            <Card>
              <CardContent className="text-center py-12">
                <Receipt className="h-12 w-12 mx-auto mb-4 text-muted-foreground opacity-50" />
                <h3 className="text-lg font-medium mb-2">No expenses yet</h3>
                <p className="text-muted-foreground mb-4">
                  Start adding expenses to this group.
                </p>
                <Button asChild>
                  <Link to={`/add-expense?group=${id}`}>
                    <Plus className="h-4 w-4 mr-2" />
                    Add First Expense
                  </Link>
                </Button>
              </CardContent>
            </Card>
          ) : expenses.map((expense) => (
            <Card key={expense.id}>
              <CardContent className="p-4">
                <div className="flex items-start justify-between">
                  <div className="flex items-start gap-3">
                    <div className="w-10 h-10 bg-muted rounded-lg flex items-center justify-center text-lg">
                      {getCategoryIcon(expense.category)}
                    </div>
                    <div className="flex-1">
                      <div className="flex items-center gap-2 mb-1">
                        <h3 className="font-medium">{expense.title}</h3>
                        {expense.receipt && (
                          <Badge variant="outline" className="text-xs">
                            <Receipt className="h-3 w-3 mr-1" />
                            Receipt
                          </Badge>
                        )}
                      </div>
                      <p className="text-sm text-muted-foreground mb-2">{expense.description}</p>
                      <div className="flex items-center gap-4 text-sm text-muted-foreground">
                        <span>{expense.category}</span>
                        <span>•</span>
                        <span>{new Date(expense.date).toLocaleDateString()}</span>
                        <span>•</span>
                        <span>Paid by {expense.paidBy.name}</span>
                      </div>
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="text-lg font-bold">${expense.amount.toFixed(2)}</div>
                    <div className="text-sm text-muted-foreground">
                      ${(expense.amount / expense.splitAmong.length).toFixed(2)} per person
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </TabsContent>

        <TabsContent value="balances" className="space-y-4">
          {/* Settlements */}
          <Card>
            <CardHeader>
              <CardTitle>Settlements</CardTitle>
              <CardDescription>Who owes whom</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {settlements.map((settlement, index) => (
                <div key={index} className="flex items-center justify-between p-3 bg-muted/50 rounded-lg">
                  <div className="flex items-center gap-3">
                    <Avatar className="h-8 w-8">
                      <AvatarImage src={settlement.from.id === '1' ? groupData.members[0].avatar : ''} />
                      <AvatarFallback>{settlement.from.name.charAt(0)}</AvatarFallback>
                    </Avatar>
                    <div className="text-sm">
                      <span className="font-medium">{settlement.from.name}</span>
                      <span className="text-muted-foreground"> owes </span>
                      <span className="font-medium">{settlement.to.name}</span>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="font-bold text-red-600">${settlement.amount.toFixed(2)}</span>
                    <Badge variant={settlement.status === 'pending' ? 'secondary' : 'default'}>
                      {settlement.status}
                    </Badge>
                  </div>
                </div>
              ))}
            </CardContent>
          </Card>

          {/* Individual Balances */}
          <Card>
            <CardHeader>
              <CardTitle>Individual Balances</CardTitle>
              <CardDescription>Each member's balance in this group</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              {groupData.members.map((member) => (
                <div key={member.id} className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <Avatar className="h-8 w-8">
                      <AvatarImage src={member.avatar} alt={member.name} />
                      <AvatarFallback>{member.name.charAt(0)}</AvatarFallback>
                    </Avatar>
                    <span className="font-medium">{member.name}</span>
                  </div>
                  <span className={`font-bold ${getBalanceColor(member.balance)}`}>
                    {getBalanceText(member.balance)}
                  </span>
                </div>
              ))}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="members" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Group Members</CardTitle>
              <CardDescription>People in this expense group</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {groupData.members.map((member) => (
                <div key={member.id} className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <Avatar className="h-10 w-10">
                      <AvatarImage src={member.avatar} alt={member.name} />
                      <AvatarFallback>{member.name.charAt(0)}</AvatarFallback>
                    </Avatar>
                    <div>
                      <div className="font-medium">{member.name}</div>
                      <div className="text-sm text-muted-foreground">{member.email}</div>
                    </div>
                  </div>
                  <div className="text-right">
                    <div className={`font-medium ${getBalanceColor(member.balance)}`}>
                      {getBalanceText(member.balance)}
                    </div>
                    <div className="text-xs text-muted-foreground">
                      {member.balance > 0 ? 'is owed' : member.balance < 0 ? 'owes' : 'settled'}
                    </div>
                  </div>
                </div>
              ))}
            </CardContent>
          </Card>

          <Button 
            variant="outline" 
            className="w-full"
            onClick={() => setIsAddMemberDialogOpen(true)}
          >
            <UserPlus className="h-4 w-4 mr-2" />
            Add Member
          </Button>
          
          <AddMemberDialog
            open={isAddMemberDialogOpen}
            onOpenChange={setIsAddMemberDialogOpen}
            groupId={id || ''}
            onMemberAdded={handleMemberAdded}
          />
        </TabsContent>
      </Tabs>
    </div>
  );
}